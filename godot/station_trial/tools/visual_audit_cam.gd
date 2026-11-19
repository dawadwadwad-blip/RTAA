@tool
extends EditorScript
## Open an assembled GIS scene, then run this script with File > Run in the script editor.
## RVA_REFERENCE_MANIFEST and RVA_AUDIT_GIS_DIR can override the repository defaults.

const OUTPUT := "res://audit_renders/"
const FRAME := [286036.805939, 4156591.390745]
static var _running := false


func _run() -> void:
	if _running:
		push_error("A visual audit is already running.")
		return
	var scene := get_scene()
	var view := EditorInterface.get_editor_viewport_3d(0)
	if scene == null or view == null:
		push_error("Open an assembled Richmond GIS 3D scene before starting the audit.")
		return
	_running = true
	var anchor := scene.find_child("RVA_GIS_Origin", true, false) as Node3D
	var world_from_gis := anchor.global_transform if anchor != null else Transform3D.IDENTITY
	var repo := ProjectSettings.globalize_path("res://").path_join("../..").simplify_path()
	var refs_path := OS.get_environment("RVA_REFERENCE_MANIFEST")
	var gis_path := OS.get_environment("RVA_AUDIT_GIS_DIR")
	if refs_path.is_empty():
		refs_path = repo.path_join("outputs/rva_street_refs/reference_cameras.json")
	if gis_path.is_empty():
		gis_path = repo.path_join("outputs/rva_gis")
	var limit := maxi(0, OS.get_environment("RVA_AUDIT_LIMIT").to_int())
	await capture(EditorInterface.get_base_control(), view.find_world_3d(), world_from_gis,
			refs_path, gis_path, OUTPUT, scene.scene_file_path, limit)
	_running = false


static func read_object(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("Missing audit input " + path)
		return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if value is Dictionary:
		return value
	push_error("Invalid audit JSON " + path)
	return {}


static func ground(x: float, z: float, grid: Dictionary, data: PackedByteArray) -> float:
	var bounds: Array = grid.bounds_en_m
	var spacing: Array = grid.pixel_size_en_m
	var size: Array = grid.size_px
	var width := int(size[0])
	var height := int(size[1])
	var col := (x + float(FRAME[0]) - float(bounds[0])) / float(spacing[0]) - 0.5
	var row := (z + float(bounds[3]) - float(FRAME[1])) / float(spacing[1]) - 0.5
	if col < 0.0 or row < 0.0 or col > width - 1 or row > height - 1:
		return NAN
	var i := mini(floori(col), width - 2)
	var j := mini(floori(row), height - 2)
	var u := col - i
	var v := row - j
	var index := 2 * (j * width + i)
	var nw := float(data.decode_u16(index))
	var se := float(data.decode_u16(index + 2 * (width + 1)))
	var code: float
	if u >= v:
		var ne := float(data.decode_u16(index + 2))
		code = nw + (ne - nw) * u + (se - ne) * v
	else:
		var sw := float(data.decode_u16(index + 2 * width))
		code = nw + (se - sw) * u + (sw - nw) * v
	return float(grid.z_offset_m) + code * float(grid.z_scale_per_code_m)


static func cleanup_run(target: String, name: String) -> void:
	var generated := RegEx.create_from_string("^capture_[0-9]+_[0-9]+$")
	if generated.search(name) == null:
		return
	var directory := target.path_join(name)
	var renders := RegEx.create_from_string("^(mapillary|kartaview)_[0-9]+\\.(tmp\\.)?png$")
	for file: String in DirAccess.get_files_at(directory):
		if renders.search(file) != null:
			DirAccess.remove_absolute(directory.path_join(file))
	DirAccess.remove_absolute(directory)


static func capture(host: Node, world: World3D, world_from_gis: Transform3D, refs_path: String,
		gis_path: String, output: String, scene_path: String, limit: int = 0) -> int:
	var refs := read_object(refs_path)
	var gis := read_object(gis_path.path_join("rva_gis_manifest.json"))
	if refs.get("schema") != "rva-street-refs/1" or gis.get("schema") != "rva-gis/1":
		push_error("Run the Richmond GIS and street reference fetchers before the audit.")
		return -1
	for frame: Array in [refs.origin_grid_m_en, gis.origin_grid_m_en]:
		if frame.size() != 2 or absf(float(frame[0]) - FRAME[0]) > 0.001 or absf(float(frame[1]) - FRAME[1]) > 0.001:
			push_error("The GIS origins disagree.")
			return -1
	var grid: Dictionary = gis.heightmap
	if grid.get("surface_model") != "linear_triangles_nw_se" or grid.get("sample_position") != "pixel_center":
		push_error("Unexpected GIS terrain sampling contract.")
		return -1
	var raw := FileAccess.get_file_as_bytes(gis_path.path_join(grid.raw_little_endian_uint16))
	if int(grid.size_px[0]) < 2 or int(grid.size_px[1]) < 2 or raw.size() != 2 * int(grid.size_px[0]) * int(grid.size_px[1]):
		push_error("Heightmap R16 is missing or truncated.")
		return -1
	var target := ProjectSettings.globalize_path(output)
	if DirAccess.make_dir_recursive_absolute(target) != OK:
		push_error("Could not create the audit render directory.")
		return -1
	var ignore := target.path_join(".gdignore")
	if not FileAccess.file_exists(ignore):
		var marker := FileAccess.open(ignore, FileAccess.WRITE)
		if marker == null:
			push_error("Could not exclude audit screenshots from Godot asset import.")
			return -1
		marker.close()
	var run_name := "capture_%d_%d" % [int(Time.get_unix_time_from_system()), Time.get_ticks_usec()]
	var run_dir := target.path_join(run_name)
	if DirAccess.make_dir_absolute(run_dir) != OK:
		push_error("Could not start a new render generation.")
		return -1
	var manifest_path := target.path_join("render_manifest.json")
	var previous := read_object(manifest_path) if FileAccess.file_exists(manifest_path) else {}
	var viewport := SubViewport.new()
	viewport.world_3d = world
	viewport.world_2d = World2D.new()
	viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	host.add_child(viewport)
	var camera := Camera3D.new()
	camera.keep_aspect = Camera3D.KEEP_WIDTH
	camera.near = 0.1
	camera.far = 5000.0
	viewport.add_child(camera)
	camera.make_current()
	var safe_id := RegEx.create_from_string("^(mapillary|kartaview)_[0-9]+$")
	var rendered: Array[Dictionary] = []
	var skipped := 0
	for row: Dictionary in refs.cameras:
		if limit > 0 and rendered.size() >= limit:
			break
		var id := str(row.get("id", ""))
		var xz: Array = row.get("local_xz_m", [])
		if safe_id.search(id) == null or xz.size() != 2:
			skipped += 1
			continue
		var e := float(xz[0])
		var south := float(xz[1])
		var y := ground(e, south, grid, raw)
		if not is_finite(y):
			skipped += 1
			continue
		var aspect := clampf(float(row.width) / maxf(1.0, float(row.height)), 0.5, 3.0)
		var pixels := Vector2i(960, roundi(960.0 / aspect)) if aspect >= 1.0 else Vector2i(roundi(960.0 * aspect), 960)
		viewport.size = pixels
		camera.fov = clampf(float(row.get("horizontal_fov_deg", 75.0)), 35.0, 125.0)
		var yaw := deg_to_rad(float(row.grid_heading_deg))
		var pitch := deg_to_rad(float(row.get("pitch_deg", 0.0)))
		var forward := Vector3(sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch))
		var eye := Vector3(e, y - float(gis.origin_elevation_m) + float(row.get("camera_height_agl_m", 2.3)), south)
		camera.look_at_from_position(world_from_gis * eye, world_from_gis * (eye + forward), world_from_gis.basis.y.normalized())
		viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
		await RenderingServer.frame_post_draw
		var image := viewport.get_texture().get_image()
		if image == null or image.is_empty() or image.get_size() != pixels:
			push_error("No valid pixels for camera " + id)
			skipped += 1
			continue
		var filename := id + ".png"
		var pending := run_dir.path_join(id + ".tmp.png")
		if image.save_png(pending) != OK or DirAccess.rename_absolute(pending, run_dir.path_join(filename)) != OK:
			DirAccess.remove_absolute(pending)
			push_error("Could not write audit view " + id)
			skipped += 1
			continue
		rendered.append({"id": id, "file": run_name.path_join(filename), "source_sha256": row.sha256})
	camera.queue_free()
	viewport.queue_free()
	if rendered.is_empty():
		cleanup_run(target, run_name)
		push_error("No reference cameras rendered inside the loaded terrain.")
		return -1
	var pending_manifest := target.path_join(".render_manifest.tmp")
	var output_file := FileAccess.open(pending_manifest, FileAccess.WRITE)
	if output_file == null:
		cleanup_run(target, run_name)
		push_error("Could not write the audit render manifest.")
		return -1
	output_file.store_string(JSON.stringify({"schema": "rva-audit-renders/1", "scene": scene_path, "run": run_name,
			"render_count": rendered.size(), "skipped": skipped, "renders": rendered}, "\t"))
	var written := output_file.get_error()
	output_file.close()
	if written != OK or DirAccess.rename_absolute(pending_manifest, manifest_path) != OK:
		cleanup_run(target, run_name)
		DirAccess.remove_absolute(pending_manifest)
		push_error("Could not publish the audit render manifest.")
		return -1
	cleanup_run(target, str(previous.get("run", "")))
	print("RVA audit saved %d renders, skipped %d." % [rendered.size(), skipped])
	return rendered.size()
