@tool
extends RefCounted
## Packs a generation of GIS layers, then publishes a separate survey scene.

const Stream = preload("res://tools/gis_pilot_stream.gd")
const SurveyCamera = preload("res://tools/gis_pilot_camera.gd")
const StationDecks = preload("res://tools/gis_station_decks.gd")
const EastMain = preload("res://tools/gis_east_main.gd")
const Shift = preload("res://station_trial.gd")
const OUTPUT := "res://assets/rva_gis/pilot"
const CHUNKS := "res://assets/rva_gis/meshes"
const GRID_FACES := 126
const STATION := Vector2(-592, -348)
const STATION_OSM_ID := "osm/way/113030476"
const STATION_GLB := "authored/rva_main_street_station.glb"
const LANE_TAGS := ["lane", "track", "opposite_lane", "opposite_track"]

var _frame: Array
var _base_y: float
var _northwest: Vector2
var _spacing: Vector2
var _width: int
var _height: int
var _heights := PackedFloat32Array()
var _extent: Rect2
var _ortho_origin: Vector2
var _ortho_step: Vector2
var _ortho_size: Vector2i
var _source_dir := ""
var _tiles: Array[Dictionary] = []
var _tile_cache: Dictionary = {}
var _tile_order: Array[String] = []
var _checksums: Dictionary
var _generation := ""
var _entries: Array[Dictionary] = []
var _terrain_paths: Dictionary = {}


static func read_object(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


func build(data_dir: String, station_decks_dir: String = "", east_main_path: String = "") -> Dictionary:
	# A builder instance owns only one generation.
	if not _generation.is_empty():
		return _fail("Create a new builder for a new GIS generation.")
	_source_dir = data_dir
	var manifest_path := data_dir.path_join("rva_gis_manifest.json")
	var m := read_object(manifest_path)
	var c := read_object(CHUNKS.path_join("rva_chunks.json"))
	if m.get("schema") != "rva-gis/1" or c.get("schema") != "rva-gis-chunks/1":
		return _fail("The GIS and building manifests are required.")
	if FileAccess.get_sha256(manifest_path) != c.get("source_manifest_sha256"):
		return _fail("The building chunks do not belong to this GIS snapshot.")
	_frame = m.origin_grid_m_en
	_base_y = float(m.origin_elevation_m)
	if m.horizontal_epsg != 26918 or _frame.size() != 2 or c.origin_grid_m_en != _frame \
			or c.origin_elevation_m != m.origin_elevation_m \
			or m.godot_axis_order != ["east", "up", "south"]:
		return _fail("The GIS and building coordinate frames disagree.")
	_checksums = m.files_sha256
	if not _read_heightfield(m.heightmap) or not _read_aerial_index(m.aerial):
		return {}
	if not _check_input("rva_roads.geojson"):
		return {}
	var roads := read_object(data_dir.path_join("rva_roads.geojson"))
	if roads.get("type") != "FeatureCollection" or not roads.get("features") is Array:
		return _fail("The OSM roads file is not a GeoJSON feature collection.")
	var generation_name := "cells_%d_%d" % [int(Time.get_unix_time_from_system()), Time.get_ticks_usec()]
	_generation = OUTPUT.path_join(generation_name)
	if DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_generation)) != OK:
		return _fail("Cannot make the GIS layer directory.")
	var report := {"terrain_cells": 0, "building_layers": 0, "road_paths": 0, "bike_paths": 0,
		"east_main_paths": 0, "grade_separated": {}, "outside_or_degenerate": 0,
		"landmarks": 0, "station_decks": {}, "street_layers": 0}
	for row: int in range(0, _height - 1, GRID_FACES):
		for col: int in range(0, _width - 1, GRID_FACES):
			if not _terrain_cell(col, row, mini(_width - 1, col + GRID_FACES), mini(_height - 1, row + GRID_FACES)):
				return {}
			report.terrain_cells += 1
	for chunk: Dictionary in c.chunks:
		if not _building_layer(chunk):
			return {}
		report.building_layers += 1
	var landmarks: Array = c.get("landmarks", [])
	var replaced: Array = c.get("replaced_osm_ids", [])
	if landmarks.size() > 1 or replaced != ([] if landmarks.is_empty() else [STATION_OSM_ID]):
		return _fail("The station replacement manifest is inconsistent.")
	for landmark: Dictionary in landmarks:
		if not _station_layer(landmark):
			return {}
		report.landmarks += 1
	if not station_decks_dir.is_empty():
		var decks := StationDecks.build(station_decks_dir, _frame, _base_y, _extent, sample)
		if decks.is_empty() or not _add_layer("station_viaducts", decks.root, decks.bounds, "viaducts"):
			return {}
		_set_terrain_dependencies(decks.bounds)
		report.station_decks = decks.profiles
	if not _road_layers(roads.features, float(c.streaming_cell_m), report):
		return {}
	var streets := {}
	if not east_main_path.is_empty():
		var station_y: Variant = null if landmarks.is_empty() else landmarks[0].origin_godot_m[1]
		streets = EastMain.read_package(east_main_path, c.source_manifest_sha256, station_y)
		if streets.is_empty():
			return {}
		var points := EastMain.vertices(streets)
		var finishes := EastMain.materials(streets.palette)
		for id: String in streets.parts:
			var street := EastMain.layer(id, streets.parts[id], points, finishes, _extent)
			if street.is_empty():
				return _fail("East Main surface geometry is invalid in layer " + id)
			if not _add_layer("EastMain_" + id, street.root, street.bounds, "street"):
				return {}
			_set_terrain_dependencies(street.bounds)
			report.street_layers += 1
	var focus_xz := _extent.get_center()
	if _extent.has_point(STATION):
		focus_xz = STATION
	var focus := Vector3(focus_xz.x, sample(focus_xz) + 4, focus_xz.y)
	var world := _scene_root(c.source_manifest_sha256, report, replaced, focus)
	_add_preview(world, focus, m.attributions)
	# Capture scene and layers share one finished generation. Prior scenes stay usable on failure.
	var scene := OUTPUT.path_join("richmond_gis_pilot.tscn")
	var temporary := _generation.path_join("preview.tscn")
	if not _save_scene(world, temporary):
		return {}
	if not streets.is_empty():
		var route: Dictionary = streets.route
		var route_origin := Vector3(route.origin_en[0], 0, -float(route.origin_en[1]))
		var heading := Vector3(route.eastbound_xz[0], 0, route.eastbound_xz[1])
		var start := route_origin + heading * float(route.start_at)
		var playable := _scene_root(c.source_manifest_sha256, report, replaced, start)
		playable.name = "EastMainNightShift"
		var driver := Node3D.new()
		driver.name = "NightShift"
		driver.set_script(Shift)
		driver.set("survey_route", route)
		_own(playable, driver)
		var playable_temp := _generation.path_join("night_shift.tscn")
		var playable_scene := OUTPUT.path_join("east_main_night_shift.tscn")
		if not _save_scene(playable, playable_temp) or DirAccess.rename_absolute(
				ProjectSettings.globalize_path(playable_temp), ProjectSettings.globalize_path(playable_scene)) != OK:
			return _fail("Cannot publish the streamed Night Shift scene.")
		report.playable_scene = playable_scene
	if DirAccess.rename_absolute(ProjectSettings.globalize_path(temporary), ProjectSettings.globalize_path(scene)) != OK:
		return _fail("Cannot publish the assembled GIS scene.")
	report.scene = scene
	report.layer_paths = _entries.size()
	return report


func _scene_root(snapshot: String, report: Dictionary, replaced: Array, focus: Vector3) -> Node3D:
	var world := Node3D.new()
	world.name = "RichmondGISPilot"
	world.set_meta("source_manifest_sha256", snapshot)
	world.set_meta("gis_extent_xz", _extent)
	world.set_meta("grade_separated", report.grade_separated)
	world.set_meta("replaced_osm_ids", replaced)
	world.set_meta("station_decks", report.station_decks)
	var anchor := Node3D.new()
	anchor.name = "RVA_GIS_Origin"
	_own(world, anchor)
	var stream := Stream.new()
	stream.name = "GISLayers"
	stream.cells = _entries
	stream.preview_focus = focus
	_own(world, stream)
	return world


func sample(point: Vector2) -> float:
	var p: Vector2 = ((point - _northwest) / _spacing).clamp(Vector2.ZERO, Vector2(_width - 1, _height - 1))
	var x := mini(floori(p.x), _width - 2)
	var z := mini(floori(p.y), _height - 2)
	var u := p.x - x
	var v := p.y - z
	var i := z * _width + x
	var nw: float = _heights[i]
	var se: float = _heights[i + _width + 1]
	if u >= v:
		var ne: float = _heights[i + 1]
		return nw + (ne - nw) * u + (se - ne) * v
	var sw: float = _heights[i + _width]
	return nw + (se - sw) * u + (sw - nw) * v


func _read_heightfield(grid: Dictionary) -> bool:
	if grid.get("surface_model") != "linear_triangles_nw_se" or grid.get("sample_position") != "pixel_center":
		return _reject("Unsupported heightfield geometry.")
	var raw_path: String = grid.raw_little_endian_uint16
	if not _check_input(raw_path):
		return false
	_width = int(grid.size_px[0])
	_height = int(grid.size_px[1])
	_spacing = Vector2(grid.pixel_size_en_m[0], grid.pixel_size_en_m[1])
	var offset := float(grid.z_offset_m) - _base_y
	var scale := float(grid.z_scale_per_code_m)
	if min(_width, _height) < 2 or _spacing.x <= 0 or _spacing.y <= 0 or scale <= 0 or not is_finite(offset):
		return _reject("Invalid heightfield dimensions or scaling.")
	var raw := FileAccess.get_file_as_bytes(_source_dir.path_join(raw_path))
	if raw.size() != 2 * _width * _height:
		return _reject("The R16 size does not match the heightfield index.")
	_northwest = Vector2(float(grid.bounds_en_m[0]) - float(_frame[0]),
			float(_frame[1]) - float(grid.bounds_en_m[3])) + _spacing * 0.5
	_extent = Rect2(_northwest, _spacing * Vector2(_width - 1, _height - 1))
	_heights.resize(_width * _height)
	for i: int in range(_heights.size()):
		_heights[i] = offset + scale * raw.decode_u16(2 * i)
	return true


func _read_aerial_index(aerial: Dictionary) -> bool:
	_ortho_origin = Vector2(float(aerial.bounds_en_m[0]) - float(_frame[0]),
			float(_frame[1]) - float(aerial.bounds_en_m[3]))
	_ortho_step = Vector2(aerial.pixel_size_en_m[0], aerial.pixel_size_en_m[1])
	_ortho_size = Vector2i(aerial.size_px[0], aerial.size_px[1])
	if min(_ortho_step.x, _ortho_step.y) <= 0 or min(_ortho_size.x, _ortho_size.y) < 1:
		return _reject("Invalid aerial dimensions.")
	var coverage := Rect2i(Vector2i.ZERO, _ortho_size)
	var total_area := 0
	for entry: Dictionary in aerial.tiles:
		var path: String = entry.path
		if not _check_input(path):
			return false
		var rect := Rect2i(Vector2i(entry.offset_px[0], entry.offset_px[1]), Vector2i(entry.size_px[0], entry.size_px[1]))
		if not coverage.encloses(rect) or not rect.has_area():
			return _reject("Aerial tile extent lies outside the mosaic.")
		var local_nw := _ortho_origin + Vector2(rect.position) * _ortho_step
		var local_se := _ortho_origin + Vector2(rect.end) * _ortho_step
		var tile_nw := Vector2(float(entry.bounds_en_m[0]) - float(_frame[0]), float(_frame[1]) - float(entry.bounds_en_m[3]))
		var tile_se := Vector2(float(entry.bounds_en_m[2]) - float(_frame[0]), float(_frame[1]) - float(entry.bounds_en_m[1]))
		if tile_nw.distance_to(local_nw) > 0.01 or tile_se.distance_to(local_se) > 0.01:
			return _reject("Aerial tile bounds do not match its pixel offsets.")
		for other: Dictionary in _tiles:
			if rect.intersects(other.rect):
				return _reject("Aerial tile extents overlap.")
		total_area += rect.get_area()
		_tiles.append({"path": path, "rect": rect})
	if total_area != coverage.get_area():
		return _reject("The aerial mosaic has gaps.")
	return true


func _crop_aerial(bounds: Rect2i) -> Image:
	var dst := Image.create_empty(bounds.size.x, bounds.size.y, false, Image.FORMAT_RGB8)
	var count := 0
	for tile: Dictionary in _tiles:
		var rect: Rect2i = tile.rect
		var region := bounds.intersection(rect)
		if not region.has_area():
			continue
		var path: String = tile.path
		var source: Image = _tile_cache.get(path)
		if source == null:
			source = Image.load_from_file(_source_dir.path_join(path))
			if source == null or source.get_size() != rect.size:
				_reject("Unable to open the expected aerial tile " + path)
				return null
			source.convert(Image.FORMAT_RGB8)
			if _tile_order.size() >= 4:
				_tile_cache.erase(_tile_order.pop_front())
			_tile_order.append(path)
			_tile_cache[path] = source
		dst.blit_rect(source, Rect2i(region.position - rect.position, region.size), region.position - bounds.position)
		count += region.get_area()
	if count != bounds.get_area():
		_reject("Terrain footprint lies beyond its aerial mosaic.")
		return null
	dst.generate_mipmaps()
	return dst


func _terrain_cell(x0: int, z0: int, x1: int, z1: int) -> bool:
	var start := _northwest + Vector2(x0, z0) * _spacing
	var end := _northwest + Vector2(x1, z1) * _spacing
	var a := (start - _ortho_origin) / _ortho_step
	var b := (end - _ortho_origin) / _ortho_step
	# Copy a 4-texel collar from adjacent source tiles for filtering at shared edges.
	var first := Vector2i(a.floor()) - Vector2i(4, 4)
	var last := Vector2i(b.ceil()) + Vector2i(4, 4)
	var frame := Rect2i(first, last - first).intersection(Rect2i(Vector2i.ZERO, _ortho_size))
	var image := _crop_aerial(frame)
	if image == null:
		return false
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uv := PackedVector2Array()
	var index := PackedInt32Array()
	var nx := x1 - x0 + 1
	for z: int in range(z0, z1 + 1):
		for x: int in range(x0, x1 + 1):
			var p := _northwest + Vector2(x, z) * _spacing
			var left := maxi(0, x - 1)
			var right := mini(_width - 1, x + 1)
			var up := maxi(0, z - 1)
			var down := mini(_height - 1, z + 1)
			var slope_e := (_heights[z * _width + right] - _heights[z * _width + left]) / ((right - left) * _spacing.x)
			var slope_s := (_heights[down * _width + x] - _heights[up * _width + x]) / ((down - up) * _spacing.y)
			vertices.append(Vector3(p.x - start.x, _heights[z * _width + x], p.y - start.y))
			normals.append(Vector3(-slope_e, 1, -slope_s).normalized())
			uv.append(((p - _ortho_origin) / _ortho_step - Vector2(frame.position)) / Vector2(frame.size))
			if z < z1 and x < x1:
				var i := (z - z0) * nx + (x - x0)
				index.append_array([i, i + 1, i + nx + 1, i, i + nx + 1, i + nx])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_INDEX] = index
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var material := StandardMaterial3D.new()
	material.albedo_texture = ImageTexture.create_from_image(image)
	material.roughness = 0.96
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	mesh.surface_set_material(0, material)
	var part := Node3D.new()
	part.position = Vector3(start.x, 0, start.y)
	var terrain := MeshInstance3D.new()
	terrain.name = "Ground"
	terrain.mesh = mesh
	_own(part, terrain)
	var body := StaticBody3D.new()
	body.name = "TerrainCollision"
	_own(part, body)
	var collider := CollisionShape3D.new()
	collider.shape = mesh.create_trimesh_shape()
	_own(part, collider, body)
	var name := "terrain_%d_%d" % [x0, z0]
	_terrain_paths[Vector2i(x0 / GRID_FACES, z0 / GRID_FACES)] = _generation.path_join(name + ".scn")
	return _add_layer(name, part, Rect2(start, end - start), "terrain")


func _building_layer(chunk: Dictionary) -> bool:
	var id: String = chunk.id
	var path: String = chunk.glb
	if not id.is_valid_identifier() or path != id + ".glb":
		return _reject("Unexpected building chunk filename.")
	var resource_path := CHUNKS.path_join(path)
	if not FileAccess.file_exists(resource_path) or FileAccess.get_sha256(resource_path) != chunk.sha256:
		return _reject("Missing or altered building chunk " + path)
	var asset := ResourceLoader.load(resource_path, "PackedScene") as PackedScene
	if asset == null:
		return _reject("Import the building GLBs in the editor first.")
	var part := Node3D.new()
	var instance := asset.instantiate() as Node3D
	var o: Array = chunk.origin_godot_m
	instance.position = Vector3(o[0], o[1], o[2])
	_own(part, instance)
	var a: Array = chunk.world_bounds_godot_m[0]
	var b: Array = chunk.world_bounds_godot_m[1]
	var bounds := Rect2(Vector2(a[0], a[2]), Vector2(b[0] - a[0], b[2] - a[2]))
	part.set_meta("neighborhood", chunk.neighborhood)
	part.set_meta("building_count", chunk.counts.buildings)
	if not _add_layer("buildings_" + id, part, bounds, "buildings"):
		return false
	_set_terrain_dependencies(bounds)
	return true


func _station_layer(landmark: Dictionary) -> bool:
	if landmark.get("id") != "main_street_station" or landmark.get("replaces_osm_id") != STATION_OSM_ID \
			or landmark.get("glb") != STATION_GLB:
		return _reject("Unexpected Main Street Station replacement.")
	var path := CHUNKS.path_join(STATION_GLB)
	if not FileAccess.file_exists(path) or FileAccess.get_sha256(path) != landmark.get("sha256"):
		return _reject("The authored Main Street Station asset is missing or its checksum changed.")
	var corners: Array = landmark.world_bounds_godot_m
	var bounds := Rect2(Vector2(corners[0][0], corners[0][2]),
			Vector2(corners[1][0] - corners[0][0], corners[1][2] - corners[0][2]))
	if not _extent.grow(0.01).encloses(bounds):
		return _reject("Main Street Station crosses the available GIS terrain boundary.")
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(path, state) != OK:
		return _reject("Could not read the authored station GLB.")
	var asset := document.generate_scene(state) as Node3D
	if asset == null:
		return _reject("Could not instance the authored station GLB.")
	var b: Array = landmark.basis_godot_columns
	var o: Array = landmark.origin_godot_m
	var alignment := Transform3D(Basis(Vector3(b[0][0], b[0][1], b[0][2]),
			Vector3(b[1][0], b[1][1], b[1][2]), Vector3(b[2][0], b[2][1], b[2][2])),
			Vector3(o[0], o[1], o[2]))
	asset.name = "StationExterior"
	asset.transform = alignment
	var part := Node3D.new()
	_own(part, asset)
	var collision_count := 0
	for child: Node in asset.get_children():
		var mesh := child as MeshInstance3D
		if mesh == null:
			part.free()
			return _reject("The station GLB must contain six direct mesh nodes.")
		mesh.owner = part
		var name := str(mesh.name).replace("_", "").replace(" ", "").to_lower()
		if name not in ["mssheadhouse", "mssmainstreetforecourt"]:
			continue
		# Bake the small survey scale differences into the collision vertices.
		var geometry_to_world := alignment * mesh.transform
		var faces := mesh.mesh.get_faces()
		for i: int in range(faces.size()):
			faces[i] = geometry_to_world.basis * faces[i]
		var shape := ConcavePolygonShape3D.new()
		shape.set_faces(faces)
		var body := StaticBody3D.new()
		body.name = "ForecourtCollision" if name == "mssmainstreetforecourt" else "HeadhouseCollision"
		body.position = geometry_to_world.origin
		_own(part, body)
		var collision := CollisionShape3D.new()
		collision.shape = shape
		_own(part, collision, body)
		collision_count += 1
	if asset.get_child_count() != 6 or collision_count != 2:
		part.free()
		return _reject("The authored station mesh or collision set is incomplete.")
	part.set_meta("replaces_osm_id", STATION_OSM_ID)
	part.set_meta("station_alignment", alignment)
	if not _add_layer("main_street_station", part, bounds, "landmark"):
		return false
	_set_terrain_dependencies(bounds)
	return true


func _set_terrain_dependencies(bounds: Rect2) -> void:
	var cell_step := _spacing * GRID_FACES
	var first := Vector2i(((bounds.position - _northwest) / cell_step).floor())
	var last := Vector2i(((bounds.end - _northwest) / cell_step).floor())
	var support := PackedStringArray()
	for z: int in range(first.y, last.y + 1):
		for x: int in range(first.x, last.x + 1):
			var tile := Vector2i(x, z)
			if _terrain_paths.has(tile):
				support.append(_terrain_paths[tile])
	_entries[-1]["terrain_dependencies"] = support


static func _grade(tags: Dictionary) -> String:
	if str(tags.get("bridge", "no")) not in ["no", "0", "false"]:
		return "bridge"
	if str(tags.get("tunnel", "no")) not in ["no", "0", "false"] or tags.get("location") == "underground":
		return "tunnel"
	if str(tags.get("layer", "0")).to_int() != 0:
		return "nonzero_layer"
	return ""


func _road_layers(features: Array, cell_size: float, report: Dictionary) -> bool:
	var buckets: Dictionary = {}
	for feature: Dictionary in features:
		var props: Dictionary = feature.properties
		var tags: Dictionary = props.tags
		var highway := str(tags.get("highway", ""))
		var id: String = feature.id
		var unsupported := _grade(tags)
		if not unsupported.is_empty():
			report.grade_separated[id] = unsupported
			continue
		if tags.get("area") == "yes" or highway in ["", "construction", "proposed"]:
			continue
		var points := PackedVector2Array()
		for position: Array in props.get("centerline_local_xz_m", []):
			var p := Vector2(position[0], position[1])
			if points.is_empty() or points[-1].distance_squared_to(p) > 0.0001:
				points.append(p)
		if points.size() < 2 or not _fits(points):
			report.outside_or_degenerate += 1
			continue
		var center: Vector2 = points[points.size() / 2]
		var cell := Vector2i((center / cell_size).floor())
		if not buckets.has(cell):
			buckets[cell] = {"root": Node3D.new(), "bounds": Rect2(points[0], Vector2.ZERO)}
		var bucket: Dictionary = buckets[cell]
		var path_group: Node3D = bucket.root
		var kind := "bike" if highway == "cycleway" else "road"
		if kind == "road":
			report.road_paths += 1
			if tags.get("name") == "East Main Street":
				report.east_main_paths += 1
		else:
			report.bike_paths += 1
		_add_path(path_group, points, id, tags, kind, "center")
		bucket.bounds = _expand(bucket.bounds, points)
		if kind != "road" or tags.get("bicycle") in ["no", "private", "dismount"]:
			continue
		for side: String in ["left", "right"]:
			var lane := _lane(tags, side)
			if lane not in LANE_TAGS:
				continue
			var offset := _bike_offset(tags, side, lane)
			var shifted := _offset_line(points, offset)
			if not _fits(shifted):
				report.outside_or_degenerate += 1
				continue
			_add_path(path_group, shifted, id, tags, "bike", side)
			bucket.bounds = _expand(bucket.bounds, shifted)
			report.bike_paths += 1
	for cell: Vector2i in buckets:
		var bucket: Dictionary = buckets[cell]
		if not _add_layer("routes_%d_%d" % [cell.x, cell.y], bucket.root, bucket.bounds, "paths"):
			return false
	return true


static func _lane(tags: Dictionary, side: String) -> String:
	var explicit: Variant = tags.get("cycleway:" + side, tags.get("cycleway:both"))
	if explicit != null:
		return str(explicit)
	var lane: String = tags.get("cycleway", "")
	var one_way: String = tags.get("oneway", "")
	if one_way == "" and tags.get("junction") in ["roundabout", "circular"]:
		one_way = "yes"
	if lane.begins_with("opposite_"):
		return lane if side == ("right" if one_way == "-1" else "left") else ""
	if one_way == "-1" and side == "right" or one_way in ["yes", "1", "true"] and side == "left":
		return ""
	return lane


static func _bike_offset(tags: Dictionary, side: String, lane: String) -> float:
	var width: String = str(tags.get("width", "")).strip_edges().trim_suffix("m").strip_edges()
	var fallback := clampi(str(tags.get("lanes", "2")).to_int(), 1, 12) * 3.0
	var meters := clampf(width.to_float(), 2.5, 50) if width.is_valid_float() else fallback
	var offset := meters * 0.5 + (1.6 if lane.ends_with("track") else -0.8)
	return -offset if side == "left" else offset


static func _offset_line(points: PackedVector2Array, offset: float) -> PackedVector2Array:
	var shifted := PackedVector2Array()
	for i: int in range(points.size()):
		var prev := (points[i] - points[maxi(i - 1, 0)]).normalized()
		var next := (points[mini(i + 1, points.size() - 1)] - points[i]).normalized()
		var right1 := Vector2(-prev.y, prev.x) if i > 0 else Vector2(-next.y, next.x)
		var right2 := Vector2(-next.y, next.x) if i + 1 < points.size() else right1
		var middle := (right1 + right2).normalized()
		if middle.is_zero_approx():
			middle = right1
		var miter := 1.0 / maxf(0.58, middle.dot(right1))
		shifted.append(points[i] + middle * offset * miter)
	return shifted


func _add_path(parent: Node3D, points: PackedVector2Array, id: String, tags: Dictionary, kind: String,
		side: String) -> void:
	var curve := Curve3D.new()
	curve.bake_interval = 2
	var first := points[0]
	curve.add_point(Vector3(first.x, sample(first), first.y))
	for i: int in range(1, points.size()):
		var a := points[i - 1]
		var b := points[i]
		# A draped segment is piecewise linear only at the terrain triangle edges.
		var p := (a - _northwest) / _spacing
		var q := (b - _northwest) / _spacing
		var stops: Array[float] = [1.0]
		_collect_crossings(p.x, q.x, stops)
		_collect_crossings(p.y, q.y, stops)
		_collect_crossings(p.x - p.y, q.x - q.y, stops)
		stops.sort()
		var previous := 0.0
		for t: float in stops:
			if t - previous < 0.00001 or (t < 1.0 and 1.0 - t < 0.00001):
				continue
			var at := a.lerp(b, t)
			curve.add_point(Vector3(at.x, sample(at), at.y))
			previous = t
	var path := Path3D.new()
	path.name = (kind + "_" + id.replace("/", "_") + "_" + side).validate_node_name()
	path.curve = curve
	path.set_meta("osm_id", id)
	path.set_meta("osm_tags", tags)
	path.set_meta("path_kind", kind)
	path.set_meta("bike_side", side)
	_own(parent, path)


static func _collect_crossings(a: float, b: float, result: Array[float]) -> void:
	var delta := b - a
	if absf(delta) < 0.00001:
		return
	for k: int in range(floori(minf(a, b)) + 1, ceili(maxf(a, b))):
		var t := (k - a) / delta
		if t > 0.00001 and t < 0.99999:
			result.append(t)


func _fits(points: PackedVector2Array) -> bool:
	for p: Vector2 in points:
		if not _extent.grow(0.0001).has_point(p):
			return false
	return true


static func _expand(bounds: Rect2, points: PackedVector2Array) -> Rect2:
	for p: Vector2 in points:
		bounds = bounds.expand(p)
	return bounds


func _add_preview(world: Node3D, focus: Vector3, credits: Dictionary) -> void:
	var camera := SurveyCamera.new()
	camera.name = "SurveyCamera"
	camera.focus = focus
	camera.extent = _extent
	camera.position = focus + Vector3(46, 188, 147)
	camera.rotation = Vector3(-0.9, 0.25, 0)
	camera.far = 3000
	camera.fov = 60.0
	camera.current = true
	_own(world, camera)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-53, -29, 0)
	sun.light_energy = 0.58
	sun.shadow_enabled = true
	_own(world, sun)
	var atmosphere := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#829eaf")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("#dae8ed")
	environment.ambient_light_energy = 0.35
	atmosphere.environment = environment
	_own(world, atmosphere)
	var overlay := CanvasLayer.new()
	_own(world, overlay)
	var label := Label.new()
	label.text = "Richmond GIS Pilot\nWASD pan · right mouse orbit · scroll zoom\n" + str(credits.vectors) + "\n" + str(credits.elevation) + " · " + str(credits.imagery)
	label.position = Vector2(16, 14)
	label.add_theme_font_size_override("font_size", 15)
	label.add_theme_color_override("font_shadow_color", Color.BLACK)
	label.add_theme_constant_override("shadow_offset_x", 1)
	label.add_theme_constant_override("shadow_offset_y", 2)
	_own(world, label, overlay)


func _check_input(relative: String) -> bool:
	if relative.is_absolute_path() or relative != relative.simplify_path() or relative.begins_with(".."):
		return _reject("Unsafe GIS source path.")
	var expected: String = _checksums.get(relative, "")
	if expected.is_empty() or FileAccess.get_sha256(_source_dir.path_join(relative)) != expected:
		return _reject("Missing or altered GIS source " + relative)
	return true


func _add_layer(name: String, part: Node3D, bounds: Rect2, kind: String) -> bool:
	part.name = name.validate_node_name()
	var path := _generation.path_join(name + ".scn")
	if not _save_scene(part, path):
		return false
	_entries.append({"path": path, "bounds": bounds, "kind": kind})
	return true


static func _own(root: Node, item: Node, parent: Node = null) -> void:
	(parent if parent != null else root).add_child(item)
	item.owner = root


static func _save_scene(root: Node, path: String) -> bool:
	var packed := PackedScene.new()
	var status := packed.pack(root)
	root.free()
	if status == OK:
		status = ResourceSaver.save(packed, path, ResourceSaver.FLAG_COMPRESS)
	if status != OK:
		return _reject("Cannot save " + path + " (" + error_string(status) + ")")
	return true


static func _reject(message: String) -> bool:
	push_error(message)
	return false


static func _fail(message: String) -> Dictionary:
	push_error(message)
	return {}
