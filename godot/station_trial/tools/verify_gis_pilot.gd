extends SceneTree
## Run this against a Godot project with the pilot GLBs already imported.
## Set RVA_GIS_DATA_DIR to the pilot GIS snapshot on disk.

const Builder = preload("res://tools/gis_pilot_builder.gd")


func _initialize() -> void:
	call_deferred("_verify")


func _verify() -> void:
	var data := OS.get_environment("RVA_GIS_DATA_DIR")
	var builder := Builder.new()
	var result := builder.build(data, OS.get_environment("RVA_GIS_STATION_DECKS_DIR"))
	if result.is_empty():
		_fail("Could not assemble the GIS scene.")
		return
	var packed := load(result.scene) as PackedScene
	var scene := packed.instantiate() as Node3D
	var stream: Node = scene.get_node("GISLayers")
	var osm := Builder.read_object(data.path_join("rva_roads.geojson"))
	var originals := {}
	for row: Dictionary in osm.features:
		originals[row.id] = row.properties.get("centerline_local_xz_m", [])
	var seams := {}
	var checks := {"seam_vertices": 0, "paths": 0, "bike_paths": 0, "east_main": 0, "east_franklin_bike": 0,
		"grounded_buildings": 0, "foundation_vertices": 0, "landmarks": 0}
	var probes := PackedVector3Array()
	for entry: Dictionary in stream.cells:
		var layer := (load(entry.path) as PackedScene).instantiate() as Node3D
		var valid := true
		match entry.kind:
			"terrain":
				valid = _verify_terrain(layer, entry.bounds, seams, checks, builder)
			"paths":
				valid = _verify_paths(layer, originals, checks, probes, scene.get_meta("grade_separated"), builder)
			"landmark":
				valid = _verify_station_asset(layer)
				checks.landmarks += 1
			"buildings":
				root.add_child(layer)
				valid = _verify_buildings(layer, checks, builder)
				root.remove_child(layer)
		layer.free()
		if not valid:
			scene.free()
			_fail("Layer failed validation " + str(entry.path))
			return
	if (checks.seam_vertices == 0 or checks.paths != result.road_paths or checks.east_main != result.east_main_paths
			or checks.bike_paths != result.bike_paths or checks.east_main == 0 or checks.east_franklin_bike == 0
			or checks.grounded_buildings != result.building_layers or checks.landmarks != result.landmarks):
		scene.free()
		_fail("Incomplete terrain, street or building verification.")
		return
	print("PASS: ", checks.seam_vertices, " shared terrain border vertices match; ground imagery has mipmaps.")
	print("PASS: ", checks.paths, " ground paths, ", checks.east_main, " East Main paths, ", checks.bike_paths,
			" bike paths (", checks.east_franklin_bike, " East Franklin lane paths), and ",
			result.grade_separated.size(), " grade-separated source ways held out.")
	print("PASS: Sampled ", checks.foundation_vertices, " grounded wall vertices across all ",
			checks.grounded_buildings, " building layers.")

	root.add_child(scene)
	var camera := scene.get_node("SurveyCamera") as Camera3D
	camera.set_process(false)
	var initial: Array = stream.loaded_paths()
	if initial.is_empty() or initial.size() >= stream.cells.size():
		_fail("The first camera did not load a limited set of surrounding cells.")
		return
	# Direct raycasts from just above the ground avoid roofs or elevated collision at the same XZ.
	await physics_frame
	await physics_frame
	if checks.landmarks == 1 and not _verify_station_collision(stream, builder):
		_fail("The authored station is missing stair collision or has a duplicate generic volume.")
		return
	if not result.station_decks.is_empty() and not _verify_deck_collision(stream, builder):
		_fail("The station viaduct collision and grade separation checks failed.")
		return
	var hits := 0
	var space := root.world_3d.direct_space_state
	for probe: Vector3 in probes:
		if Vector2(probe.x - stream.preview_focus.x, probe.z - stream.preview_focus.z).length() > 310:
			continue
		var query := PhysicsRayQueryParameters3D.create(probe + Vector3.UP * 0.25, probe - Vector3.UP * 0.25)
		var hit := space.intersect_ray(query)
		if hit.is_empty() or hit.collider.name != "TerrainCollision":
			continue
		if absf(hit.position.y - probe.y) > 0.003:
			_fail("Terrain collision differs from the East Main road elevation.")
			return
		hits += 1
	if hits < 12:
		_fail("Insufficient physical road alignment probes.")
		return
	print("PASS: ", hits, " East Main raycasts align with rendered terrain under ",
			ProjectSettings.get_setting("physics/3d/physics_engine"), ".")
	var extent: Rect2 = scene.get_meta("gis_extent_xz")
	var far := Vector3(extent.end.x - 55, 0, extent.end.y - 55)
	stream.set_focus(far)
	for i: int in range(115):
		await process_frame
		await create_timer(0.014).timeout
	var after: Array = stream.loaded_paths()
	var arrived := 0
	var retired := 0
	for path: String in after:
		if path not in initial:
			arrived += 1
	for path: String in initial:
		if path not in after:
			retired += 1
	if arrived < 1 or retired < 1:
		_fail("Camera movement did not replace streamed cells.")
		return
	for entry: Dictionary in stream.cells:
		if entry.path not in after:
			continue
		for support: String in entry.get("terrain_dependencies", []):
			if support not in after:
				_fail("A streamed building layer is missing its supporting terrain.")
				return
	print("PASS: Stream loaded ", initial.size(), "/", stream.cells.size(), " layers at startup, then added ",
			arrived, " and unloaded ", retired, " at a distant focus with building support intact.")
	print("PILOT: ", result.scene)
	scene.queue_free()
	await process_frame
	quit()


func _verify_terrain(layer: Node3D, bounds: Rect2, seams: Dictionary, checks: Dictionary, builder: RefCounted) -> bool:
	var mesh: ArrayMesh = layer.get_node("Ground").mesh
	var mat := mesh.surface_get_material(0) as StandardMaterial3D
	if mat.albedo_texture == null:
		return false
	var tex: Image = mat.albedo_texture.get_image()
	if tex == null or tex.is_empty() or not tex.has_mipmaps():
		return false
	var arrays := mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	for i: int in range(vertices.size()):
		var p := layer.position + vertices[i]
		if absf(p.y - builder.sample(Vector2(p.x, p.z))) > 0.003:
			return false
		if not Rect2(Vector2.ZERO, Vector2.ONE).has_point(uv[i]):
			return false
		if minf(absf(p.x - bounds.position.x), absf(p.x - bounds.end.x)) > 0.001 and \
				minf(absf(p.z - bounds.position.y), absf(p.z - bounds.end.y)) > 0.001:
			continue
		var key := Vector2i(roundi(p.x * 1000), roundi(p.z * 1000))
		if seams.has(key):
			if absf(p.y - seams[key][0]) > 0.00001 or normals[i].distance_to(seams[key][1]) > 0.0001:
				return false
			checks.seam_vertices += 1
		else:
			seams[key] = [p.y, normals[i]]
	return true


func _verify_paths(layer: Node3D, originals: Dictionary, checks: Dictionary, probes: PackedVector3Array,
		held_out: Dictionary, builder: RefCounted) -> bool:
	for path: Path3D in layer.get_children():
		var id: String = path.get_meta("osm_id")
		var curve := path.curve
		var tags: Dictionary = path.get_meta("osm_tags")
		var side: String = path.get_meta("bike_side")
		var is_bike: bool = path.get_meta("path_kind") == "bike"
		var east_main: bool = tags.get("name") == "East Main Street" and not is_bike
		if held_out.has(id) or not originals.has(id) or curve.point_count < 2:
			return false
		var origin: Array = originals[id][0]
		var first := curve.get_point_position(0)
		if side == "center" and Vector2(first.x, first.z).distance_to(Vector2(origin[0], origin[1])) > 0.015:
			return false
		for i: int in range(1, curve.point_count):
			var a := curve.get_point_position(i - 1)
			var b := curve.get_point_position(i)
			var point := (a + b) * 0.5
			if absf(point.y - builder.sample(Vector2(point.x, point.z))) > 0.005:
				return false
			if east_main and i % 4 == 0:
				probes.append(point)
		if is_bike:
			checks.bike_paths += 1
			if tags.get("name") == "East Franklin Street" and side in ["left", "right"]:
				checks.east_franklin_bike += 1
		else:
			checks.paths += 1
			if east_main:
				checks.east_main += 1
	return true


func _verify_buildings(layer: Node3D, checks: Dictionary, builder: RefCounted) -> bool:
	var count := 0
	for mesh: MeshInstance3D in layer.find_children("*", "MeshInstance3D", true, false):
		for i: int in range(mesh.mesh.get_surface_count()):
			var mat := mesh.mesh.surface_get_material(i)
			if mat == null or not mat.resource_name.begins_with("M_Facade_"):
				continue
			var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(i)[Mesh.ARRAY_VERTEX]
			for v: Vector3 in vertices:
				var p := mesh.global_transform * v
				var ground: float = builder.sample(Vector2(p.x, p.z))
				if absf(p.y - ground + 0.06) < 0.018:
					count += 1
	if count == 0:
		return false
	checks.foundation_vertices += count
	checks.grounded_buildings += 1
	return true


func _verify_station_asset(layer: Node3D) -> bool:
	var exterior := layer.get_node_or_null("StationExterior")
	if exterior == null or exterior.get_child_count() != 6:
		return false
	var textured := {}
	var glazed := false
	for mesh: MeshInstance3D in exterior.get_children():
		for i: int in range(mesh.mesh.get_surface_count()):
			var mat := mesh.mesh.surface_get_material(i) as StandardMaterial3D
			if mat == null:
				return false
			for image: Texture2D in [mat.albedo_texture, mat.normal_texture]:
				if image != null and image.get_width() > 1:
					textured[image] = true
			glazed = glazed or (mat.resource_name == "MSS Train shed glazing"
					and mat.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED)
	if textured.size() != 8 or not glazed:
		return false
	print("PASS: The saved landmark contains six authored meshes, eight textures and transparent glazing.")
	return true


func _verify_station_collision(stream: Node, builder: RefCounted) -> bool:
	var station := stream.get_node_or_null("main_street_station") as Node3D
	if station == null or station.get_meta("replaces_osm_id") != "osm/way/113030476":
		return false
	var alignment: Transform3D = station.get_meta("station_alignment")
	var space := root.world_3d.direct_space_state
	for i: int in range(15):
		var step := alignment * Vector3(15.25, -2.58 + 0.2 * i, 10.36 - 0.283 * i - 0.14)
		var probe := PhysicsRayQueryParameters3D.create(step + Vector3.UP * 0.09, step - Vector3.UP * 0.09)
		var hit := space.intersect_ray(probe)
		if hit.is_empty() or hit.collider.name != "ForecourtCollision" or absf(hit.position.y - step.y) > 0.007:
			return false
	# This point lies through the middle of the replaced shed footprint.
	var ground := Vector2(-635.72, -400.63)
	var y: float = builder.sample(ground)
	var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(
		Vector3(ground.x, 60, ground.y), Vector3(ground.x, y - 0.1, ground.y)))
	if hit.is_empty() or hit.collider.name != "TerrainCollision" or absf(hit.position.y - y) > 0.003:
		return false
	print("PASS: Jolt matched all 15 station treads and found no generic shed collision.")
	return true


func _verify_deck_collision(stream: Node, builder: RefCounted) -> bool:
	var viaducts := stream.get_node_or_null("station_viaducts")
	if viaducts == null or viaducts.get_meta("profiles", {}).size() != 4:
		return false
	var space := root.world_3d.direct_space_state
	var counts := {"highway": 0, "rail": 0, "held": 0}
	for row: Dictionary in viaducts.get_meta("collision_probes"):
		var p: Vector3 = row.point
		var ray := PhysicsRayQueryParameters3D.create(p + Vector3.UP * 0.2, p - Vector3.UP * 0.2)
		var hit := space.intersect_ray(ray)
		if row.collidable:
			if hit.is_empty() or hit.collider.name != row.body or absf(hit.position.y - p.y) > 0.008:
				push_error(str(row.body) + " failed a collision interval at " + str(p))
				return false
			var key := "rail" if row.kind == "rail" else "highway"
			counts[key] += 1
		else:
			if not hit.is_empty() or row.kind != "rail":
				return false
			counts.held += 1
	var crossings: Array = viaducts.get_meta("east_main_crossings")
	if crossings.size() != 4 or counts.highway == 0 or counts.rail == 0 or counts.held == 0:
		return false
	for row: Dictionary in crossings:
		var p: Vector2 = row.xz
		var deck := Vector3(p.x, row.deck_y, p.y)
		var ground := Vector3(p.x, builder.sample(p), p.y)
		var deck_hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(
			deck + Vector3.UP * 0.2, deck - Vector3.UP * 0.2))
		var ground_hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(
			ground + Vector3.UP * 0.2, ground - Vector3.UP * 0.2))
		if (ground_hit.is_empty() or ground_hit.collider.name != "TerrainCollision"
				or absf(ground_hit.position.y - ground.y) > 0.004 or deck.y - ground.y < 7.0):
			return false
		if row.collidable:
			if deck_hit.is_empty() or deck_hit.collider.name != row.body or absf(deck_hit.position.y - deck.y) > 0.07:
				return false
		elif not deck_hit.is_empty():
			return false
		print("SPACING: ", row.body, " top is ", "%.3f" % (deck.y - ground.y), " m above the GIS ground.")
	print("PASS: ", counts.highway, " supported highway intervals and ", counts.rail, " observed rail intervals",
		" have deck collision. ", counts.held, " rail intervals remain visual only. East Main stays at grade.")
	return true


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
