extends Camera3D
## Survey camera for the generated scene. XZ is the independent streaming focus.

@export var focus := Vector3.ZERO
@export var extent := Rect2()
var _distance := 240.0
var _yaw := 0.25
var _pitch := 0.9


func _ready() -> void:
	_update_view()


func _process(delta: float) -> void:
	var dx := float(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT))
	dx -= float(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT))
	var dz := float(Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN))
	dz -= float(Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP))
	var step := Vector3(dx, 0, dz).limit_length().rotated(Vector3.UP, _yaw) * delta * _distance * 0.64
	if step != Vector3.ZERO:
		focus += step
		focus.x = clampf(focus.x, extent.position.x, extent.end.x)
		focus.z = clampf(focus.z, extent.position.y, extent.end.y)
		_update_view()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_distance = maxf(30, _distance * 0.86)
			_update_view()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_distance = minf(360, _distance / 0.86)
			_update_view()
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
		_yaw -= event.relative.x * 0.005
		_pitch = clampf(_pitch + event.relative.y * 0.005, 0.28, 1.4)
		_update_view()


func _update_view() -> void:
	var offset := Vector3(0, sin(_pitch), cos(_pitch)).rotated(Vector3.UP, _yaw) * _distance
	look_at_from_position(focus + offset, focus, Vector3.UP)
	get_parent().get_node("GISLayers").set_focus(focus)
