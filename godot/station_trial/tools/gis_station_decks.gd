@tool
extends RefCounted
## Imports the locked station preview's narrow OBJ/MTL dialect and keeps
## collision on the supported top-surface triangles of each separate deck.

const SOURCE_ORIGIN := [286036.805939, 4156591.390745]
const MESH_FILE := "RVA_Station_Decks.obj"
const MATERIAL_FILE := "RVA_Station_Decks.mtl"
const KINDS := {
	"I95_West_Mainline": "road",
	"I95_East_Mainline": "road",
	"I95_East_Ramp": "ramp",
	"Bellwood_Rail_Trestle": "rail",
}


static func build(directory: String, origin: Array, elevation_zero: float, terrain_bounds: Rect2,
		ground_height: Callable) -> Dictionary:
	var report_path := directory.path_join("station_decks.json")
	if not FileAccess.file_exists(report_path):
		return _fail("Missing station_decks.json in " + directory)
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(report_path))
	if (not data is Dictionary or data.get("schema_version") != 1
			or data.get("mode") != "local_lidar_to_dem_visual_preview"
			or data.get("horizontal_crs") != "EPSG:26918"):
		return _fail("The station deck preview must use the RVA EPSG:26918 profile export.")
	var source_origin: Array = data.get("origin_grid_m_en", SOURCE_ORIGIN)
	if source_origin != SOURCE_ORIGIN or float(data.get("origin_navd88_m", 0)) != 0.0:
		return _fail("Unexpected station deck origin.")
	var paths := [directory.path_join(MESH_FILE), directory.path_join(MATERIAL_FILE)]
	var geometry: Dictionary = data.geometry
	if (geometry.mesh != MESH_FILE or geometry.material != MATERIAL_FILE
			or FileAccess.get_sha256(paths[0]) != geometry.sha256
			or FileAccess.get_sha256(paths[1]) != geometry.material_sha256):
		return _fail("The station deck geometry differs from its report.")
	var materials := _materials(FileAccess.get_file_as_string(paths[1]))
	if materials.is_empty():
		return _fail("The station deck material palette is empty.")
	var offset := Vector3(float(source_origin[0]) - float(origin[0]), -elevation_zero,
			float(origin[1]) - float(source_origin[1]))
	var parsed := _parse_mesh(FileAccess.get_file_as_string(paths[0]), materials, offset,
			terrain_bounds, ground_height)
	if (parsed.is_empty() or parsed.vertices.size() != int(geometry.vertices)
			or parsed.face_count != int(geometry.faces)):
		return _fail("The station deck mesh is incomplete or outside the survey terrain.")
	var root := Node3D.new()
	var profiles := {}
	var samples: Array[Dictionary] = []
	var crossings: Array[Dictionary] = []
	for profile: Dictionary in data.profiles:
		var id: String = profile.name
		if (not KINDS.has(id) or profiles.has(id) or profile.kind != KINDS[id]
				or not parsed.groups.has(id + "_Surface")):
			root.free()
			return _fail("Unexpected station deck profile " + id)
		var body := _add_profile(root, profile, parsed, materials, offset, samples, crossings)
		if body.is_empty():
			root.free()
			return _fail("The station deck surface does not match its profile " + id)
		profiles[id] = body
	if profiles.size() != KINDS.size():
		root.free()
		return _fail("The viaduct export must contain all four station profiles.")
	root.set_meta("profiles", profiles)
	root.set_meta("collision_probes", samples)
	root.set_meta("east_main_crossings", crossings)
	return {"root": root, "bounds": parsed.bounds, "profiles": profiles}


static func _materials(source: String) -> Dictionary:
	var out := {}
	var name := ""
	for row: String in source.split("\n", false):
		var words := row.strip_edges().split(" ", false)
		if words.is_empty():
			continue
		if words[0] == "newmtl" and words.size() == 2:
			name = words[1]
		elif words[0] == "Kd" and words.size() == 4 and not name.is_empty():
			var material := StandardMaterial3D.new()
			material.resource_name = name
			material.albedo_color = Color(float(words[1]), float(words[2]), float(words[3]))
			material.roughness = 0.85
			out[name] = material
	return out


static func _parse_mesh(source: String, materials: Dictionary, offset: Vector3,
		terrain_bounds: Rect2, ground_height: Callable) -> Dictionary:
	var vertices := PackedVector3Array()
	var groups := {}
	var group := ""
	var material := ""
	var count := 0
	var support_vertex := 0
	var bounds := Rect2()
	for row: String in source.split("\n", false):
		var words := row.strip_edges().split(" ", false)
		if words.is_empty():
			continue
		match words[0]:
			"o":
				if words.size() != 2 or groups.has(words[1]):
					return {}
				group = words[1]
				groups[group] = []
				support_vertex = 0
			"usemtl":
				if words.size() != 2 or not materials.has(words[1]):
					return {}
				material = words[1]
			"v":
				if words.size() != 4 or group.is_empty():
					return {}
				var v := Vector3(float(words[1]), float(words[3]), -float(words[2])) + offset
				var xz := Vector2(v.x, v.z)
				if not v.is_finite() or not terrain_bounds.has_point(xz):
					return {}
				if group.ends_with("_Illustrative_Supports"):
					# The old column exporter records four base corners then four
					# top corners. Seat the visual pier bases in the current DEM.
					if support_vertex % 8 < 4:
						v.y = ground_height.call(xz) - 0.35
					support_vertex += 1
				bounds = Rect2(xz, Vector2.ZERO) if vertices.is_empty() else bounds.expand(xz)
				vertices.append(v)
			"f":
				if group.is_empty() or material.is_empty() or words.size() not in [4, 5]:
					return {}
				var indices := PackedInt32Array()
				for i: int in range(1, words.size()):
					var index := words[i].to_int() - 1
					if index < 0 or index >= vertices.size():
						return {}
					indices.append(index)
				groups[group].append({"indices": indices, "material": material})
				count += 1
	return {"vertices": vertices, "groups": groups, "bounds": bounds, "face_count": count}


static func _add_profile(root: Node3D, profile: Dictionary, parsed: Dictionary, materials: Dictionary,
		offset: Vector3, probes: Array[Dictionary], crossings: Array[Dictionary]) -> Dictionary:
	var id: String = profile.name
	var rail: bool = profile.kind == "rail"
	var source_samples: Array = profile.samples
	var surface: Array = parsed.groups[id + "_Surface"]
	var supports: Array = parsed.groups.get(id + "_Illustrative_Supports", [])
	var vertices: PackedVector3Array = parsed.vertices
	var strip_material := "deck_ballast" if rail else "deck_asphalt"
	if source_samples.size() < 2:
		return {}
	var parts := {}
	var normals := {}
	var collision_faces := PackedVector3Array()
	var intervals := 0
	var supported := 0
	for face: Dictionary in surface + supports:
		var indices: PackedInt32Array = face.indices
		var key: String = face.material
		var a := vertices[indices[0]]
		var b := vertices[indices[1]]
		var c := vertices[indices[2]]
		var normal := (b - a).cross(c - a).normalized()
		if normal.is_zero_approx():
			return {}
		var use_collision := false
		if key == strip_material and normal.y > 0.5:
			if intervals + 1 >= source_samples.size() or indices.size() != 4:
				return {}
			var left: Dictionary = source_samples[intervals]
			var right: Dictionary = source_samples[intervals + 1]
			var start := _profile_point(left, offset)
			var end := _profile_point(right, offset)
			if (a.lerp(b, 0.5).distance_to(start) > 0.004
					or c.lerp(vertices[indices[3]], 0.5).distance_to(end) > 0.004):
				return {}
			use_collision = left.raw_class17_median_m != null and right.raw_class17_median_m != null
			if use_collision:
				supported += 1
			probes.append({"body": id + "Collision", "point": start.lerp(end, 0.5),
				"collidable": use_collision, "kind": profile.kind})
			intervals += 1
		if not parts.has(key):
			parts[key] = PackedVector3Array()
			normals[key] = PackedVector3Array()
		var points: PackedVector3Array = parts[key]
		var directions: PackedVector3Array = normals[key]
		for i: int in range(1, indices.size() - 1):
			# Godot's mesh front faces use clockwise vertex order.
			var tri := PackedVector3Array([a, vertices[indices[i + 1]], vertices[indices[i]]])
			points.append_array(tri)
			directions.append_array([normal, normal, normal])
			if use_collision:
				collision_faces.append_array(tri)
		parts[key] = points
		normals[key] = directions
	if (intervals != source_samples.size() - 1 or supported == 0 or (not rail and supported != intervals)):
		return {}
	var mesh := ArrayMesh.new()
	for key: String in parts:
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = parts[key]
		arrays[Mesh.ARRAY_NORMAL] = normals[key]
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(mesh.get_surface_count() - 1, materials[key])
	var structure := MeshInstance3D.new()
	structure.name = id
	structure.mesh = mesh
	root.add_child(structure)
	structure.owner = root
	var body := StaticBody3D.new()
	body.name = id + "Collision"
	root.add_child(body)
	body.owner = root
	var collision := CollisionShape3D.new()
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(collision_faces)
	collision.shape = shape
	body.add_child(collision)
	collision.owner = root
	var crossing: Dictionary = profile.east_main
	var en: Array = crossing.local_en_m
	var xy := Vector2(float(en[0]) + offset.x, -float(en[1]) + offset.z)
	crossings.append({"body": body.name, "xz": xy,
		"deck_y": float(crossing.deck_z_m_in_preview) + offset.y,
		"collidable": crossing.support == "bracketed_by_observed_returns"})
	return {"intervals": intervals, "collision_intervals": supported,
		"held_intervals": intervals - supported, "preview_length_m": profile.length_m,
		"routing_ready": false, "osm_ways": profile.osm_ways}


static func _profile_point(row: Dictionary, offset: Vector3) -> Vector3:
	var en: Array = row.local_en_m
	return Vector3(en[0], row.preview_deck_z_m, -float(en[1])) + offset


static func _fail(message: String) -> Dictionary:
	push_error(message)
	return {}
