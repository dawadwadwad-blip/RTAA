extends SceneTree


func _initialize() -> void:
	verify.call_deferred()


func ticks(count: int) -> void:
	for i in count:
		await physics_frame


func tap(action: StringName) -> void:
	Input.action_press(action)
	await ticks(2)
	Input.action_release(action)
	await ticks(2)


func capture(trial: Node, path: String) -> Error:
	trial.set_physics_process(false)
	await process_frame
	await process_frame
	RenderingServer.force_draw()
	var result := root.get_texture().get_image().save_png(path)
	trial.set_physics_process(true)
	return result


func verify() -> void:
	var trial = load("res://station_trial.tscn").instantiate()
	root.add_child(trial)
	await ticks(8)
	if not trial.initialized:
		push_error("Trial did not start")
		quit(1)
		return
	if DisplayServer.get_name() != "headless":
		var screenshot := OS.get_environment("RVA_TRIAL_SCREENSHOT")
		if not screenshot.is_empty():
			trial.speedometer.text = "0 mph"
			if await capture(trial, screenshot) != OK:
				push_error("Could not write the trial screenshot")
				quit(1)
				return
	for index in 2:
		await tap("station_view")
		if trial.view_index != index or not trial.view_label.visible:
			push_error("Station camera could not be selected")
			quit(1)
			return
		var path := OS.get_environment("RVA_TRIAL_STATION_VIEWS")
		if DisplayServer.get_name() != "headless" and not path.is_empty():
			if await capture(trial, "%s%d.png" % [path, index + 1]) != OK:
				push_error("Station camera capture failed")
				quit(1)
				return
	await tap("station_view")
	if trial.view_index != -1 or trial.view_label.visible:
		push_error("Driving camera did not return after the two station views")
		quit(1)
		return
	var crosswalk_height: float = trial.surface_height(Vector3.ZERO)
	var hill_height: float = trial.surface_height(trial.route_position(-65.0, 0.0))
	if absf(crosswalk_height - 5.998) > 0.025 or hill_height < crosswalk_height + 1.1:
		push_error("Crosswalk or west grade is missing")
		quit(1)
		return
	await tap("quality")
	if trial.sun.shadow_enabled or not is_equal_approx(root.scaling_3d_scale, 0.75):
		push_error("The low graphics preset did not apply")
		quit(1)
		return
	await tap("quality")
	Input.action_press("gas")
	await ticks(360)
	Input.action_release("gas")
	if trial.pieces != 0 or trial.phase != trial.Shift.READY:
		push_error("An unarmed crossing started painting")
		quit(1)
		return
	await tap("retry")
	await tap("stripe")
	Input.action_press("gas")
	await ticks(445)
	Input.action_release("gas")
	if trial.phase != trial.Shift.COMPLETE or trial.pieces != 44 or trial.progress != 22.0:
		push_error("The 22 m shift did not complete after passing both gates")
		quit(1)
		return
	await tap("retry")
	if trial.phase != trial.Shift.READY or trial.pieces != 0 or trial.laid.get_child_count() != 0:
		push_error("Retry did not restore a fresh shift")
		quit(1)
		return
	print("PASS: Crosswalk %.3f m, west grade %.3f m, graphics toggle, unarmed drive, full 22 m pass and clean retry." % [crosswalk_height, hill_height])
	quit()
