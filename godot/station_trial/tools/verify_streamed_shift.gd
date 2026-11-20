extends SceneTree
## Play the saved streamed Night Shift through the real input and physics loop.

const TRIAL := "res://assets/rva_gis/pilot/east_main_night_shift.tscn"


func _initialize() -> void:
	verify.call_deferred()


func ticks(count: int) -> void:
	for i: int in range(count):
		await physics_frame


func tap(action: StringName) -> void:
	Input.action_press(action)
	await ticks(3)
	Input.action_release(action)
	await ticks(4)


func verify() -> void:
	var world := (load(TRIAL) as PackedScene).instantiate()
	root.add_child(world)
	var shift: Node = world.get_node("NightShift")
	var stream: Node = world.get_node("GISLayers")
	await ticks(9)
	if not shift.initialized or shift.start_at != 530 or not is_finite(shift.truck.position.y):
		fail("The generated truck could not spawn on the 21st Street asphalt.")
		return
	var initial: Array = stream.loaded_paths()
	var checked := 0
	shift.set_physics_process(false)
	if world.get_meta("east_main_dressing_layers", 0) > 0 and not await verify_dressing(shift, stream):
		return
	for chainage: int in range(0, 533, 4):
		var model: Vector3 = shift.route_position(chainage, -3.15)
		if chainage % 108 == 0:
			stream.load_now(shift.to_global(model))
			await ticks(3)
		var floor_y: float = shift.surface_height(model)
		if not is_finite(floor_y):
			fail("No drivable East Main asphalt at %d m." % chainage)
			return
		checked += 1
	shift.set_physics_process(true)
	print("PASS: ", checked, " westbound lane checks cover the road transitions and underpass.")
	await tap("retry")
	for index: int in range(2):
		await tap("station_view")
		if shift.view_index != index or not shift.view_label.visible:
			fail("A station inspection camera did not load.")
			return
		var target: Array = shift.station_views[index].target
		var aim: Vector3 = shift.to_global(Vector3(target[0], target[1], target[2]))
		if not aimed_at(shift.camera, aim):
			fail("A station camera was aimed in the wrong coordinate frame.")
			return
	await tap("station_view")
	var look_ahead: Vector3 = shift.to_global(shift.truck.position + shift.heading() * 12.0 + Vector3.UP * 3.6)
	if shift.view_index != -1 or not aimed_at(shift.camera, look_ahead):
		fail("The driving camera did not return to the westbound view.")
		return
	await tap("quality")
	if shift.sun.shadow_enabled or not is_equal_approx(root.scaling_3d_scale, 0.75):
		fail("The streamed scene did not switch to the low graphics preset.")
		return
	await tap("quality")
	await tap("stripe")
	Input.action_press("gas")
	var elapsed := 0
	while elapsed < 3900 and shift.phase != shift.Shift.COMPLETE:
		await ticks(1)
		elapsed += 1
	Input.action_release("gas")
	if shift.phase != shift.Shift.COMPLETE or shift.pieces != 44 or shift.progress != 22.0 or not shift.gates_ready:
		fail("Night Shift failed before the green cones at %.2f m." % shift.truck.position.dot(shift.eastbound))
		return
	var current: Array = stream.loaded_paths()
	var retired := 0
	for path: String in initial:
		if path not in current:
			retired += 1
	if retired == 0:
		fail("The drive did not retire any of the starting layers.")
		return
	await tap("retry")
	if shift.phase != shift.Shift.READY or shift.pieces != 0 or not is_finite(shift.truck.position.y):
		fail("Retry did not clear the pass and return the truck to a loaded road.")
		return
	print("PASS: Drove 525 m from 21st Street, completed the 22 m Night Shift pass, and reset. ",
		retired, " starting layers retired during the drive.")
	quit()


func verify_dressing(shift: Node, stream: Node) -> bool:
	# The original shell collision is the independent reference for the baked storefronts.
	var physics: PhysicsDirectSpaceState3D = shift.get_world_3d().direct_space_state
	var checked := 0
	var checked_layers := {}
	for along: float in [40.0, 530.0]:
		stream.load_now(shift.to_global(shift.route_position(along, -3.15)))
		await ticks(3)
		for layer: Node in stream.get_children():
			if not layer.has_meta("frontages") or checked_layers.has(layer.name):
				continue
			checked_layers[layer.name] = true
			for probe: Dictionary in layer.get_meta("frontages"):
				var p := Vector3(probe.point[0], probe.point[1], probe.point[2])
				var n := Vector3(probe.normal[0], 0, probe.normal[2])
				var query := PhysicsRayQueryParameters3D.create(p + n * 0.33, p - n * 0.05, 1)
				var hit := physics.intersect_ray(query)
				if hit.is_empty() or hit.position.distance_to(p) > 0.035:
					fail("Dressing face missed the GIS building shell at " + str(probe.osm_id))
					return false
				checked += 1
	if checked == 0 or checked_layers.size() != stream.get_parent().get_meta("east_main_dressing_layers"):
		fail("The baked storefront layers were not all streamed.")
		return false
	if shift.parked_vehicles.is_empty():
		fail("The streamed route lost its parked-vehicle clearance data.")
		return false
	for car: Array in shift.parked_vehicles:
		if not shift.parked_overlap(car[0], car[1]) or shift.parked_overlap(car[0], -3.15):
			fail("Incorrect parked-vehicle clearance on the Night Shift lane.")
			return false
	print("PASS: ", checked, " dressed wall faces match the original shell and ",
		shift.parked_vehicles.size(), " parked vehicles clear the shift lane.")
	return true


func aimed_at(camera: Camera3D, point: Vector3) -> bool:
	return (-camera.global_basis.z).dot(camera.global_position.direction_to(point)) > 0.999


func fail(message: String) -> void:
	push_error(message)
	quit(1)
