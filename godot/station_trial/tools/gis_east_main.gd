@tool
extends RefCounted
## Assemble the authored, already terrain-split East Main surface package.

const ROAD_LAYER := 2
const ROAD_FINISHES := ["approach_asphalt", "approach_brick", "approach_white", "approach_yellow", "corridor_road"]
const ASPHALT_NOISE := 64


static func read_package(path: String, snapshot_sha: String, station_y: Variant) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("The authored East Main surface package is missing.")
		return {}
	var doc: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if (not doc is Dictionary or doc.get("schema") != "rva-gis-east-main/1"
			or doc.get("snapshot_sha256") != snapshot_sha or doc.get("station_y_m") != station_y
			or not doc.get("parts") is Dictionary or not doc.get("vertices") is Array):
		push_error("The East Main package must match the GIS snapshot and station alignment.")
		return {}
	return doc


static func vertices(doc: Dictionary) -> PackedVector3Array:
	var points := PackedVector3Array()
	for p: Array in doc.vertices:
		points.append(Vector3(p[0], p[1], p[2]))
	return points


static func materials(palette: Dictionary) -> Dictionary:
	var finishes := {}
	var asphalt := _asphalt_texture()
	var brick := _brick_texture()
	for key: String in palette:
		var material := StandardMaterial3D.new()
		material.resource_name = key
		material.albedo_color = Color(palette[key])
		material.roughness = 0.9
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		if key in ["approach_asphalt", "corridor_road"]:
			material.albedo_texture = asphalt
		elif key == "approach_brick":
			material.albedo_texture = brick
		finishes[key] = material
	return finishes


static func layer(group: String, parts: Dictionary, points: PackedVector3Array, finishes: Dictionary,
		terrain: Rect2) -> Dictionary:
	var bounds := Rect2()
	var has_bounds := false
	var visual := ArrayMesh.new()
	var collider := PackedVector3Array()
	for key: String in parts:
		if not finishes.has(key):
			return {}
		var verts := PackedVector3Array()
		var normals := PackedVector3Array()
		var uv := PackedVector2Array()
		for face: Array in parts[key]:
			if face.size() not in [3, 4]:
				return {}
			for index: float in face:
				if index < 0 or index >= points.size():
					return {}
			var p := points[int(face[0])]
			for i: int in range(1, face.size() - 1):
				var q := points[int(face[i])]
				var r := points[int(face[i + 1])]
				var normal := (q - p).cross(r - p).normalized()
				if normal.is_zero_approx():
					continue
				var tri := [p, r, q]
				for position: Vector3 in tri:
					var xz := Vector2(position.x, position.z)
					if not terrain.has_point(xz) or not position.is_finite():
						return {}
					bounds = bounds.expand(xz) if has_bounds else Rect2(xz, Vector2.ZERO)
					has_bounds = true
					uv.append(xz / (1.15 if key == "approach_brick" else 4.0))
				verts.append_array(tri)
				normals.append_array([normal, normal, normal])
				if ((group == "East_Main_Approach_Road" and key in ROAD_FINISHES)
						or key == "corridor_road") and normal.y > 0.1:
					collider.append_array(tri)
		if verts.is_empty():
			continue
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_NORMAL] = normals
		arrays[Mesh.ARRAY_TEX_UV] = uv
		visual.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		visual.surface_set_material(visual.get_surface_count() - 1, finishes[key])
	if not has_bounds:
		return {}
	var root := Node3D.new()
	var surface := MeshInstance3D.new()
	surface.mesh = visual
	root.add_child(surface)
	surface.owner = root
	if not collider.is_empty():
		var road := StaticBody3D.new()
		road.name = "EastMainRoad"
		road.collision_layer = ROAD_LAYER
		root.add_child(road)
		road.owner = root
		var shape := ConcavePolygonShape3D.new()
		shape.set_faces(collider)
		var polygon := CollisionShape3D.new()
		polygon.shape = shape
		road.add_child(polygon)
		polygon.owner = root
	return {"root": root, "bounds": bounds}


static func _asphalt_texture() -> ImageTexture:
	var image := Image.create_empty(ASPHALT_NOISE, ASPHALT_NOISE, false, Image.FORMAT_RGB8)
	var random := RandomNumberGenerator.new()
	random.seed = 1462
	for y: int in range(ASPHALT_NOISE):
		for x: int in range(ASPHALT_NOISE):
			var value := random.randf_range(0.68, 1.0)
			image.set_pixel(x, y, Color(value, value, value))
	image.generate_mipmaps()
	return ImageTexture.create_from_image(image)


static func _brick_texture() -> ImageTexture:
	var image := Image.create_empty(128, 128, false, Image.FORMAT_RGB8)
	for y: int in range(128):
		var row := y / 16
		for x: int in range(128):
			var column := (x + (row % 2) * 16) / 32
			var mortar := y % 16 < 2 or (x + (row % 2) * 16) % 32 < 2
			var surface := Color(0.64, 0.61, 0.55) if mortar else Color.WHITE.lerp(
				Color(0.51, 0.42, 0.37), float((row * 13 + (column % 4) * 7) % 11) / 11.0)
			image.set_pixel(x, y, surface)
	image.generate_mipmaps()
	return ImageTexture.create_from_image(image)
