"""Export a street-scale Godot scene from the assembled station Blender file."""

import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "godot" / "station_trial" / "assets"
BOUNDS = (-808, 225, -613, 421)
GROUND = {"Terrain", "Roads_and_paths"}


def inside(points):
    west, south, east, north = BOUNDS
    return (max(p.x for p in points) >= west and min(p.x for p in points) <= east
            and max(p.y for p in points) >= south and min(p.y for p in points) <= north)


def crop_ground(obj):
    mesh = obj.data
    points = [obj.matrix_world @ v.co for v in mesh.vertices]
    remap, vertices, faces, materials = {}, [], [], []
    for face in mesh.polygons:
        indices = list(face.vertices)
        if not inside([points[i] for i in indices]):
            continue
        for i in indices:
            if i not in remap:
                remap[i] = len(vertices)
                vertices.append(mesh.vertices[i].co)
        faces.append([remap[i] for i in indices])
        materials.append(face.material_index)
    cropped = bpy.data.meshes.new(obj.name + " trial")
    cropped.from_pydata(vertices, [], faces)
    for material in mesh.materials:
        cropped.materials.append(material)
    for face, index in zip(cropped.polygons, materials):
        face.material_index = index
    obj.data = cropped


def export():
    report = json.loads((ROOT / "reports/station_approach.json").read_text())
    crosswalk = next(row for row in report["witnesses"] if row["name"] == "station_crosswalk")
    east, north = crosswalk["local_en_m"]
    origin = Vector((east, north, 0))
    road_axis = report["station_frame"]
    tangent = Vector((road_axis[0][0], -road_axis[1][0])).normalized()
    ASSETS.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    selected = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not inside([obj.matrix_world @ Vector(p) for p in obj.bound_box]):
            continue
        if obj.name in GROUND:
            crop_ground(obj)
        selected.append(obj)
    for obj in selected:
        transform = obj.matrix_world.copy()
        transform.translation -= origin
        obj.matrix_world = transform
        obj.select_set(True)
    if len(selected) < 12 or "FINISHED" not in bpy.ops.export_scene.gltf(
            filepath=str(ASSETS / "shockoe.glb"), export_format="GLB", use_selection=True,
            export_tangents=True, export_image_format="AUTO"):
        raise RuntimeError("Unable to export the complete station trial scene.")
    route = {"origin_en": [east, north], "eastbound_xz": list(tangent),
             "ground_meshes": ["Terrain", "Roads_and_paths", "East_Main_Approach_Road"],
             "attribution": report["attribution"]}
    (ASSETS / "route.json").write_text(json.dumps(route, indent=2) + "\n")
    print(f"PASS: Exported {len(selected)} Shockoe meshes in meters around the station crossing.")


if __name__ == "__main__":
    export()
