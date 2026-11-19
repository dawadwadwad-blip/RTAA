@tool
extends EditorScript
## Assemble a separate GIS scene from fetch_rva_gis.py and build_rva_3d_blocks.py outputs.

const Builder = preload("res://tools/gis_pilot_builder.gd")


func _run() -> void:
	var data := OS.get_environment("RVA_GIS_DATA_DIR")
	if data.is_empty():
		data = ProjectSettings.globalize_path("res://").path_join("../../outputs/rva_gis").simplify_path()
	var builder := Builder.new()
	var result := builder.build(data)
	if not result.is_empty():
		print("Built ", result.scene, " with ", result.terrain_cells, " terrain cells, ",
				result.building_layers, " building layers and ", result.road_paths, " road paths.")
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.open_scene_from_path(result.scene)
