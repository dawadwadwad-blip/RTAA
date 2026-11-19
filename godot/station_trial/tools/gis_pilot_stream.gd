@tool
extends Node3D
## Radius-based scene loading. The index stores paths, so packing the world
## scene does not load the terrain textures, building meshes or road paths.

@export var cells: Array[Dictionary] = []
@export var preview_focus := Vector3.ZERO
@export var load_radius_m := 385.0
@export var unload_margin_m := 120.0

var _resident: Dictionary = {}
var _pending: Dictionary = {}
var _failed: Dictionary = {}
var _focus := Vector3.ZERO
var _timer := 0.0


func _ready() -> void:
	load_now(preview_focus)


func set_focus(at: Vector3) -> void:
	_focus = at


func loaded_paths() -> Array:
	return _resident.keys()


func pending_count() -> int:
	return _pending.size()


func load_now(at: Vector3) -> void:
	_focus = at
	var support := _terrain_support()
	_cull(support)
	for entry: Dictionary in cells:
		var path: String = entry.path
		if _wanted(entry, support) and _has_support(entry) and not _resident.has(path) and not _failed.has(path):
			var asset: PackedScene
			if _pending.has(path):
				asset = ResourceLoader.load_threaded_get(path)
				_pending.erase(path)
			else:
				asset = ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
			_add(path, asset)


func _process(delta: float) -> void:
	if Engine.is_editor_hint():
		return
	if _pending.is_empty() and _timer > delta:
		_timer -= delta
		return
	var support := _terrain_support()
	for path: String in _pending.keys():
		var status := ResourceLoader.load_threaded_get_status(path)
		if status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
			continue
		var entry: Dictionary = _pending[path]
		_pending.erase(path)
		if status != ResourceLoader.THREAD_LOAD_LOADED:
			_add(path, null)
			continue
		var asset := ResourceLoader.load_threaded_get(path) as PackedScene
		if (_wanted(entry, support) or _distance(entry) <= load_radius_m + unload_margin_m) and _has_support(entry):
			_add(path, asset)
	_timer -= delta
	if _timer > 0:
		return
	_timer = 0.12
	_cull(support)
	var queue: Array[Dictionary] = []
	for entry: Dictionary in cells:
		if _wanted(entry, support) and _has_support(entry) and not (
				_resident.has(entry.path) or _pending.has(entry.path) or _failed.has(entry.path)):
			queue.append(entry)
	queue.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return _distance(a) < _distance(b))
	for i: int in range(mini(queue.size(), 3 - _pending.size())):
		var entry := queue[i]
		var path: String = entry.path
		var err := ResourceLoader.load_threaded_request(path, "PackedScene", false, ResourceLoader.CACHE_MODE_IGNORE)
		if err == OK:
			_pending[path] = entry
		else:
			_add(path, null)


func _distance(entry: Dictionary) -> float:
	var bounds: Rect2 = entry.bounds
	var p := Vector2(_focus.x, _focus.z)
	var nearest := p.clamp(bounds.position, bounds.end)
	return p.distance_to(nearest)


func _wanted(entry: Dictionary, support: Dictionary) -> bool:
	var radius := load_radius_m + (150.0 if entry.kind == "terrain" else 0.0)
	return support.has(entry.path) or _distance(entry) <= radius


func _terrain_support() -> Dictionary:
	var paths := {}
	for entry: Dictionary in cells:
		if entry.kind != "buildings":
			continue
		var margin := unload_margin_m if _resident.has(entry.path) else 0.0
		if _distance(entry) <= load_radius_m + margin:
			for path: String in entry.terrain_dependencies:
				paths[path] = true
	return paths


func _has_support(entry: Dictionary) -> bool:
	for path: String in entry.get("terrain_dependencies", []):
		if not _resident.has(path):
			return false
	return true


func _cull(support: Dictionary) -> void:
	for entry: Dictionary in cells:
		if (_resident.has(entry.path) and not _wanted(entry, support)
				and _distance(entry) > load_radius_m + unload_margin_m):
			var layer: Node = _resident[entry.path]
			remove_child(layer)
			layer.queue_free()
			_resident.erase(entry.path)


func _add(path: String, asset: PackedScene) -> void:
	if asset == null:
		_failed[path] = true
		push_error("Could not stream GIS layer " + path)
		return
	var layer := asset.instantiate()
	add_child(layer)
	_resident[path] = layer
