extends Node3D

const STREETS := "res://assets/shockoe.glb"
const SURVEY_ROAD_LAYER := preload("res://tools/gis_east_main.gd").ROAD_LAYER
const ROAD_START := 27.0
const ROAD_FINISH := 5.0
const STRIPE_LANE := -3.15
const START_AT := 37.0
const STRIPE_WIDTH := 0.15

enum Shift { READY, ARMED, PAINTING, COMPLETE }

@export var survey_route: Dictionary = {}

var phase: Shift = Shift.READY
var eastbound: Vector3
var right_eastbound: Vector3
var centerline: Array = []
var parked_vehicles: Array = []
var start_at := START_AT
var end_at := 55.0
var truck: Node3D
var camera: Camera3D
var sun: DirectionalLight3D
var speed := 0.0
var yaw := 0.0
var progress := 0.0
var laid: Node3D
var work_order: PanelContainer
var status: Label
var speedometer: Label
var controls: Label
var view_label: Label
var station_views: Array = []
var view_index := -1
var paint: StandardMaterial3D
var pieces := 0
var initialized := false
var survey_stream: Node
var gates_ready := false


func _ready() -> void:
	truck = Node3D.new()
	camera = Camera3D.new()
	sun = DirectionalLight3D.new()
	laid = Node3D.new()
	work_order = PanelContainer.new()
	var route: Dictionary = survey_route
	if route.is_empty():
		route = JSON.parse_string(FileAccess.get_file_as_string("res://assets/route.json"))
	else:
		var origin: Array = route.origin_en
		position = Vector3(origin[0], 0, -float(origin[1]))
		survey_stream = get_parent().get_node("GISLayers")
	var tangent: Array = route["eastbound_xz"]
	eastbound = Vector3(tangent[0], 0.0, tangent[1]).normalized()
	right_eastbound = Vector3(-eastbound.z, 0.0, eastbound.x)
	centerline = route.get("east_main_centerline", [])
	parked_vehicles = route.get("parking", [])
	start_at = route.get("start_at", START_AT)
	end_at = route.get("end_at", 55.0)
	station_views = route.get("station_views", [])
	register_keyboard()
	if survey_stream == null:
		var street := (load(STREETS) as PackedScene).instantiate()
		add_child(street)
		shade_street(street)
		for name in route["ground_meshes"]:
			var mesh := street.find_child(name, true, false) as MeshInstance3D
			assert(mesh != null, "Missing driving surface " + name)
			mesh.create_trimesh_collision()
	add_child(laid)
	add_child(truck)
	build_truck()
	add_child(camera)
	camera.current = true
	camera.fov = 67.0
	camera.far = 780.0
	add_lighting()
	build_hud(route["attribution"])
	paint = material(Color("93e2b1"))
	paint.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	reset_shift()
	await get_tree().physics_frame
	await get_tree().physics_frame
	var grade := surface_height(truck.position)
	if not is_finite(grade):
		status.text = "The starting road has not loaded."
		push_error("Night Shift requires collision at its starting point.")
		return
	truck.position.y = grade
	place_gates()
	update_camera(1.0)
	initialized = true


func shade_street(street: Node3D) -> void:
	var palette := {
		"approach_asphalt": Color("383b3d"), "asphalt": Color("3e4041"),
		"approach_brick": Color("97513f"), "approach_walk": Color("9b9489"),
		"approach_curb": Color("bcb3a4"), "approach_white": Color("e6dcc6"),
		"approach_yellow": Color("deb45a"), "terrain": Color("5d6a50"),
		"path": Color("877f70"),
		"deck_asphalt": Color("4f4d4b"), "deck_green_steel": Color("3f5147"),
		"deck_pier": Color("827e73"),
		"corridor_road": Color("5e5b53"), "corridor_walk": Color("a4937e"),
		"corridor_yellow": Color("dcb34e"), "corridor_white": Color("ded7c4"),
	}
	for node in street.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		for index in instance.mesh.get_surface_count():
			var surface := instance.mesh.surface_get_material(index) as StandardMaterial3D
			if surface:
				var name := surface.resource_name.get_slice(".", 0)
				if palette.has(name):
					var adjusted := surface.duplicate() as StandardMaterial3D
					adjusted.albedo_color = palette[name]
					instance.set_surface_override_material(index, adjusted)


func register_keyboard() -> void:
	var bindings := {
		"gas": [KEY_W, KEY_UP], "brake": [KEY_S, KEY_DOWN],
		"left": [KEY_A, KEY_LEFT], "right": [KEY_D, KEY_RIGHT],
		"stripe": [KEY_E], "retry": [KEY_R], "quality": [KEY_F2], "station_view": [KEY_C],
	}
	for action in bindings:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		for key in bindings[action]:
			var binding := InputEventKey.new()
			binding.physical_keycode = key
			InputMap.action_add_event(action, binding)


func reset_shift() -> void:
	view_index = -1
	truck.position = route_position(start_at, STRIPE_LANE)
	truck.position.y = 6.1
	yaw = atan2(-eastbound.x, -eastbound.z)
	truck.rotation.y = yaw
	speed = 0.0
	phase = Shift.READY
	clear_stripe()
	if initialized:
		var grade := surface_height(truck.position)
		if is_finite(grade):
			truck.position.y = grade
		update_camera(1.0)


func _physics_process(delta: float) -> void:
	if not initialized:
		return
	if Input.is_action_just_pressed("retry"):
		if survey_stream != null:
			initialized = false
			survey_stream.load_now(to_global(route_position(start_at, STRIPE_LANE)))
			await get_tree().physics_frame
			await get_tree().physics_frame
			initialized = true
		reset_shift()
		return
	if Input.is_action_just_pressed("stripe") and phase == Shift.READY:
		phase = Shift.ARMED
	if Input.is_action_just_pressed("quality"):
		sun.shadow_enabled = not sun.shadow_enabled
		get_viewport().scaling_3d_scale = 1.0 if sun.shadow_enabled else 0.75
	if Input.is_action_just_pressed("station_view") and not station_views.is_empty():
		view_index = ((view_index + 2) % (station_views.size() + 1)) - 1
		update_camera(1.0)
		if survey_stream != null:
			survey_stream.load_now(camera.global_position)
	if view_index >= 0:
		update_hud()
		return

	var throttle := Input.get_action_strength("gas")
	var brake := Input.get_action_strength("brake")
	var old_along := truck.position.dot(eastbound)
	if brake > 0.0:
		var goal := 0.0 if speed > 0.1 else -4.0
		speed = move_toward(speed, goal, 8.0 * brake * delta)
	elif throttle > 0.0:
		var striping_speed := phase == Shift.PAINTING or (phase == Shift.ARMED and old_along < ROAD_START + 22)
		var limit := 7.0 if striping_speed else 13.0
		speed = move_toward(speed, limit, 3.2 * throttle * delta)
	else:
		speed = move_toward(speed, 0.0, 2.1 * delta)

	var steering := Input.get_axis("left", "right")
	var steering_factor := minf(absf(speed) / 3.0, 1.0)
	yaw -= steering * signf(speed) * steering_factor * 0.76 * delta
	var forward := heading()
	var old_lateral := truck.position.dot(right_eastbound) - center_offset(old_along)
	var along := clampf(old_along + forward.dot(eastbound) * speed * delta, -74.0, end_at)
	var lateral := clampf(old_lateral + forward.dot(right_eastbound) * speed * delta, -6.2, 6.2)
	var destination := route_position(along, lateral)
	var grade := surface_height(destination)
	if parked_overlap(along, lateral) or not is_finite(grade):
		speed = 0.0
		along = old_along
		lateral = old_lateral
	else:
		destination.y = grade
		truck.position = destination
	truck.rotation.y = yaw
	if survey_stream != null:
		survey_stream.set_focus(truck.global_position)
	if not gates_ready and along < ROAD_START + 180.0:
		place_gates()
	advance_shift(old_along, along, lateral, forward)
	update_camera(1.0 - exp(-7.0 * delta))
	update_hud()


func heading() -> Vector3:
	return Vector3(sin(yaw), 0.0, cos(yaw))


func route_position(along: float, lateral: float) -> Vector3:
	return eastbound * along + right_eastbound * (lateral + center_offset(along))


func center_offset(along: float) -> float:
	if centerline.is_empty() or along <= 0.0:
		return 0.0
	for i in range(1, centerline.size()):
		var here: Array = centerline[i]
		if along <= float(here[0]):
			var last: Array = centerline[i - 1]
			return lerpf(last[1], here[1], inverse_lerp(last[0], here[0], along))
	return centerline.back()[1]


func parked_overlap(along: float, lateral: float) -> bool:
	for parked in parked_vehicles:
		if absf(along - parked[0]) < parked[2] + 1.85 and absf(lateral - parked[1]) < parked[3] + 0.84:
			return true
	return false


func surface_height(at: Vector3) -> float:
	var position_world := to_global(at)
	var start := Vector3(position_world.x, 100.0 if survey_stream != null else 20.0, position_world.z)
	var finish := Vector3(position_world.x, -20.0 if survey_stream != null else 0.0, position_world.z)
	var query := PhysicsRayQueryParameters3D.create(start, finish, SURVEY_ROAD_LAYER if survey_stream != null else 1)
	query.hit_back_faces = true
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		return to_local(hit.position).y
	return NAN if survey_stream != null else 6.0


func advance_shift(old_along: float, along: float, lateral: float, forward: Vector3) -> void:
	var on_line := absf(lateral - STRIPE_LANE) <= 0.95 and forward.dot(-eastbound) > 0.74
	if phase == Shift.ARMED and on_line and old_along >= ROAD_START and along < ROAD_START:
		phase = Shift.PAINTING
	if phase != Shift.PAINTING:
		return
	if not on_line or along > old_along + 0.002:
		clear_stripe()
		phase = Shift.ARMED
		return
	var distance := clampf(ROAD_START - along, 0.0, ROAD_START - ROAD_FINISH)
	while progress + 0.5 <= distance:
		var marker := route_position(ROAD_START - progress - 0.25, STRIPE_LANE)
		var grade := surface_height(marker)
		if not is_finite(grade):
			clear_stripe()
			phase = Shift.ARMED
			return
		marker.y = grade + 0.026
		var stroke := box(laid, marker, Vector3(STRIPE_WIDTH, 0.025, 0.505), paint)
		stroke.rotation.y = atan2(eastbound.x, eastbound.z)
		progress += 0.5
		pieces += 1
	if along <= ROAD_FINISH:
		phase = Shift.COMPLETE


func clear_stripe() -> void:
	for piece in laid.get_children():
		laid.remove_child(piece)
		piece.queue_free()
	progress = 0.0
	pieces = 0


func place_gates() -> void:
	if gates_ready:
		return
	var positions: Array[Vector3] = []
	for along: float in [ROAD_START, ROAD_FINISH]:
		for lateral: float in [STRIPE_LANE, STRIPE_LANE - 1.10, STRIPE_LANE + 1.10]:
			var point := route_position(along, lateral)
			point.y = surface_height(point)
			if not is_finite(point.y):
				return
			positions.append(point)
	add_gate(positions.slice(0, 3), Color("f5bd61"))
	add_gate(positions.slice(3, 6), Color("93e2b1"))
	gates_ready = true


func add_gate(points: Array[Vector3], tint: Color) -> void:
	var mark := material(tint)
	mark.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var bar := box(self, points[0] + Vector3.UP * 0.035, Vector3(1.55, 0.042, 0.29), mark)
	bar.rotation.y = atan2(eastbound.x, eastbound.z)
	var cone := CylinderMesh.new()
	cone.top_radius = 0.035
	cone.bottom_radius = 0.16
	cone.height = 0.62
	cone.radial_segments = 8
	for index in [1, 2]:
		mesh_instance(self, cone, points[index] + Vector3.UP * 0.32, mark)


func update_camera(amount: float) -> void:
	if view_index >= 0:
		var view: Dictionary = station_views[view_index]
		var eye: Array = view["eye"]
		var target: Array = view["target"]
		camera.fov = view["fov"]
		camera.position = Vector3(eye[0], eye[1], eye[2])
		camera.look_at(to_global(Vector3(target[0], target[1], target[2])))
		return
	camera.fov = 67.0
	var forward := heading()
	var right := Vector3(-forward.z, 0.0, forward.x)
	var eye := truck.position - forward * 8.7 + Vector3.UP * 4.15 + right * 0.55
	camera.position = camera.position.lerp(eye, amount)
	camera.look_at(to_global(truck.position + forward * 12.0 + Vector3.UP * 3.6))


func add_lighting() -> void:
	var world := WorldEnvironment.new()
	var atmosphere := Environment.new()
	var sky := Sky.new()
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("497798")
	sky_material.sky_horizon_color = Color("cdd8d8")
	sky_material.ground_bottom_color = Color("9b9983")
	sky_material.ground_horizon_color = Color("cdd8d8")
	sky.sky_material = sky_material
	atmosphere.sky = sky
	atmosphere.background_mode = Environment.BG_SKY
	atmosphere.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	atmosphere.ambient_light_color = Color("c1d1e2")
	atmosphere.ambient_light_energy = 0.53
	atmosphere.fog_enabled = true
	atmosphere.fog_light_color = Color("cdd8d8")
	atmosphere.fog_density = 0.0017
	atmosphere.fog_sky_affect = 0.0
	world.environment = atmosphere
	add_child(world)
	sun.rotation_degrees = Vector3(-44.0, 24.0, 0.0)
	sun.light_color = Color("ffe1bd")
	sun.light_energy = 0.87
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 85.0
	add_child(sun)


func material(color: Color) -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.roughness = 0.86
	return result


func mesh_instance(parent: Node3D, mesh: Mesh, location: Vector3, surface: Material) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = location
	instance.material_override = surface
	parent.add_child(instance)
	return instance


func box(parent: Node3D, location: Vector3, size: Vector3, surface: Material) -> MeshInstance3D:
	var geometry := BoxMesh.new()
	geometry.size = size
	return mesh_instance(parent, geometry, location, surface)


func build_truck() -> void:
	var orange := material(Color("e0a046"))
	var charcoal := material(Color("303438"))
	var window := material(Color("688795"))
	var bumper := material(Color("afb4ae"))
	var light := material(Color("f6dc9c"))
	var tail := material(Color("b33326"))
	box(truck, Vector3(0, 0.68, 0), Vector3(1.88, 0.24, 4.08), charcoal)
	box(truck, Vector3(0, 1.04, 0.87), Vector3(1.91, 0.62, 1.94), orange)
	box(truck, Vector3(0, 1.62, 0.68), Vector3(1.77, 0.58, 1.18), orange)
	box(truck, Vector3(0, 1.65, 1.274), Vector3(1.57, 0.45, 0.03), window)
	box(truck, Vector3(0, 1.64, 0.08), Vector3(1.52, 0.37, 0.035), window)
	box(truck, Vector3(0, 0.88, -1.06), Vector3(1.88, 0.29, 1.90), orange)
	box(truck, Vector3(0, 1.14, -1.27), Vector3(1.34, 0.31, 0.94), charcoal)
	box(truck, Vector3(0, 0.59, 2.04), Vector3(1.98, 0.20, 0.16), bumper)
	box(truck, Vector3(0, 0.62, -2.03), Vector3(1.98, 0.23, 0.15), bumper)
	box(truck, Vector3(0, 2.0, 0.46), Vector3(0.86, 0.13, 0.21), light)
	var wheel := CylinderMesh.new()
	wheel.height = 0.27
	wheel.top_radius = 0.39
	wheel.bottom_radius = 0.39
	wheel.radial_segments = 14
	for side in [-1.0, 1.0]:
		var x := float(side)
		box(truck, Vector3(x * 0.899, 1.64, 0.70), Vector3(0.026, 0.37, 0.81), window)
		box(truck, Vector3(x * 1.03, 1.43, 1.05), Vector3(0.17, 0.17, 0.15), charcoal)
		box(truck, Vector3(x * 0.68, 0.85, 1.845), Vector3(0.28, 0.16, 0.035), light)
		box(truck, Vector3(x * 0.77, 0.82, -2.019), Vector3(0.21, 0.12, 0.03), tail)
		for z in [-1.26, 1.29]:
			var tire := mesh_instance(truck, wheel, Vector3(x * 0.89, 0.39, z), charcoal)
			tire.rotation.z = PI * 0.5


func build_hud(attribution: String) -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var hud := Control.new()
	layer.add_child(hud)
	hud.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color(0.06, 0.11, 0.13, 0.94)
	panel.border_color = Color("dcad6e")
	panel.border_width_top = 2
	panel.set_corner_radius_all(7)
	panel.content_margin_left = 19
	panel.content_margin_right = 19
	panel.content_margin_top = 13
	panel.content_margin_bottom = 15
	work_order.add_theme_stylebox_override("panel", panel)
	work_order.position = Vector2(24, 22)
	hud.add_child(work_order)
	var rows := VBoxContainer.new()
	rows.add_theme_constant_override("separation", 5)
	work_order.add_child(rows)
	var place := make_label("SHOCKOE BOTTOM  /  EAST MAIN WESTBOUND", 14, Color("d6b583"))
	rows.add_child(place)
	rows.add_child(make_label("Night Shift", 29, Color("f5f0e5")))
	status = make_label("", 17, Color("f5f0e5"))
	status.custom_minimum_size.x = 398
	rows.add_child(status)
	speedometer = make_label("", 19, Color("f5f0e5"))
	hud.add_child(speedometer)
	speedometer.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	speedometer.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	speedometer.offset_left = -230
	speedometer.offset_right = -24
	speedometer.offset_top = 24
	controls = make_label("WASD or arrows  Drive    E  Arm    R  Restart    C  Station views    F2  Graphics", 16, Color("f5f0e5"))
	hud.add_child(controls)
	controls.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	controls.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	controls.offset_left = -350
	controls.offset_right = 350
	controls.offset_top = -41
	var credit := make_label(attribution, 12, Color("d6ddd7"))
	hud.add_child(credit)
	credit.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	credit.offset_left = 23
	credit.offset_top = -24
	view_label = make_label("", 19, Color("f5f0e5"))
	hud.add_child(view_label)
	view_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	view_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	view_label.offset_left = -350
	view_label.offset_right = 350
	view_label.offset_top = -41
	if DisplayServer.is_touchscreen_available() or OS.has_feature("web"):
		add_touch_controls(hud)
	update_hud()


func make_label(value: String, size: int, tint: Color) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", tint)
	label.add_theme_color_override("font_shadow_color", Color(0.02, 0.06, 0.08, 0.86))
	label.add_theme_constant_override("outline_size", 3)
	label.add_theme_color_override("font_outline_color", Color(0.03, 0.06, 0.07, 0.76))
	return label


func add_touch_controls(hud: Control) -> void:
	for item in [["◀", "left", false, 24], ["▶", "right", false, 104],
			["Striper", "stripe", true, -344], ["Retry", "retry", true, -264],
			["Brake", "brake", true, -184], ["Drive", "gas", true, -104]]:
		var button := Button.new()
		var action := StringName(item[1])
		button.text = item[0]
		button.focus_mode = Control.FOCUS_NONE
		hud.add_child(button)
		button.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT if item[2] else Control.PRESET_BOTTOM_LEFT)
		button.offset_left = item[3]
		button.offset_right = item[3] + 72
		button.offset_top = -106
		button.offset_bottom = -52
		button.button_down.connect(func(): Input.action_press(action))
		button.button_up.connect(func(): Input.action_release(action))


func update_hud() -> void:
	var inspecting := view_index >= 0
	work_order.visible = not inspecting
	speedometer.visible = not inspecting
	controls.visible = not inspecting
	view_label.visible = inspecting
	if inspecting:
		view_label.text = "%s    ·    C  Change view" % station_views[view_index]["name"]
		return
	match phase:
		Shift.READY:
			status.text = "Drive west to Main Street Station."
		Shift.ARMED:
			if truck.position.dot(eastbound) < ROAD_START - 0.3:
				status.text = "Reverse past amber to retry the pass."
			else:
				var distance := truck.position.dot(eastbound) - ROAD_START
				status.text = "Amber cones in %d m" % roundi(distance) if distance > 12.0 else "Armed. Drive between the amber cones."
		Shift.PAINTING:
			status.text = "Stay in lane   ·   %d / %d m" % [int(progress), int(ROAD_START - ROAD_FINISH)]
		Shift.COMPLETE:
			status.text = "Work order filed. East Main is striped."
	speedometer.text = "%d mph   ·   %d FPS" % [roundi(absf(speed) * 2.23694), Engine.get_frames_per_second()]
	if not sun.shadow_enabled:
		speedometer.text += "   ·   Low"
