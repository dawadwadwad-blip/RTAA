"""Render the assembled Richmond mesh with Blender's built-in Cycles renderer."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import bpy
from mathutils import Matrix, Vector


def insert_station(scene, bundle, alignment, mesh_report):
    plan = json.loads(alignment.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1:
        raise ValueError("Expected the version 1 station alignment plan.")
    if (plan["footprint_export_sha256"] != mesh_report["building_export_sha256"]
            or plan["terrain_report_sha256"] != mesh_report["terrain_report_sha256"]):
        raise ValueError("The station and combined mesh must use the same building and terrain exports.")
    with bundle.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != plan["archive_sha256"]:
            raise ValueError("The station alignment was computed for a different ZIP.")
    placeholder = scene.objects.get(plan["replacement_object"])
    if placeholder is None:
        raise ValueError("The current mesh is missing the mapped station volume.")
    previous = set(scene.objects)
    with TemporaryDirectory() as staging, ZipFile(bundle) as archive:
        payload = archive.read(plan["asset_member"])
        if hashlib.sha256(payload).hexdigest() != plan["asset_sha256"]:
            raise ValueError("The archived station FBX differs from its lock.")
        fbx = Path(staging) / "RVA_Main_Street_Station.fbx"
        fbx.write_bytes(payload)
        bpy.ops.import_scene.fbx(filepath=str(fbx))

    models = [obj for obj in scene.objects if obj not in previous and obj.type == "MESH"]
    if len(models) != 1:
        raise ValueError("The archived station should supply exactly one mesh.")
    station = models[0]
    clock_x, clock_y = plan["legacy_clock_xy_m"]
    points = [station.matrix_world @ v.co for v in station.data.vertices]
    contact = [p.z for p in points if (p.x - clock_x)**2 + (p.y - clock_y)**2 <= 8.0**2]
    if not contact:
        raise ValueError("No station vertices were located within the clock-tower base sample.")
    a, b = plan["legacy_mesh_xy_to_pilot_en"]
    ground_offset = plan["clock_anchor_dem_m"] - min(contact) - 0.10
    transform = Matrix(((a[0], a[1], 0, a[2]), (b[0], b[1], 0, b[2]),
                        (0, 0, 1, ground_offset), (0, 0, 0, 1)))
    station.matrix_world = transform @ station.matrix_world
    station.name = "Main Street Station — landmark"
    bpy.data.objects.remove(placeholder, do_unlink=True)
    print(f"PASS: Placed Main Street Station and replaced its duplicate volume. Z adjustment {ground_offset:.2f} m.")
    return plan


def make_view(mesh_path, output, bundle=None, alignment=None, blend=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    mesh_report = json.loads((mesh_path.parent / "pilot_mesh_preview.json").read_text(encoding="utf-8"))
    with mesh_path.open("rb") as mesh:
        if hashlib.file_digest(mesh, "sha256").hexdigest() != mesh_report["mesh_sha256"]:
            raise ValueError("The preview OBJ differs from its report.")
    bpy.ops.wm.obj_import(filepath=str(mesh_path), forward_axis="Y", up_axis="Z")

    plan = insert_station(scene, bundle, alignment, mesh_report) if bundle else None
    objects = [obj for obj in scene.objects if obj.type == "MESH"]
    terrain = next(obj for obj in objects if obj.name == "Terrain")
    points = [terrain.matrix_world @ Vector(corner) for corner in terrain.bound_box]
    west, east = min(p.x for p in points), max(p.x for p in points)
    south, north = min(p.y for p in points), max(p.y for p in points)
    center = Vector(((west + east) / 2 + 15, (south + north) / 2, 6))
    if any(abs(a - b) > 0.02 for a, b in zip(
            (west, south, east, north), mesh_report["bounds_local_en_m"])):
        raise ValueError("The imported axes and terrain bounds differ from the mesh report.")

    if plan:
        eye = Vector((*plan["camera_eye_en_m"], plan["camera_eye_height_m"]))
        target = Vector((*plan["clock_anchor_en_m"], plan["clock_anchor_dem_m"] + 14))
    else:
        eye, target = center + Vector((440, -710, 720)), center
    bpy.ops.object.camera_add(location=eye)
    camera = bpy.context.object
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    if plan:
        camera.data.lens = 28
    else:
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = 1280
    camera.data.clip_end = 5000
    scene.camera = camera

    bpy.ops.object.light_add(type="SUN", location=center + Vector((-250, -350, 440)))
    sun = bpy.context.object
    sun.rotation_euler = (center - sun.location).to_track_quat("-Z", "Y").to_euler()
    sun.data.energy = 3.2
    sun.data.angle = 0.09
    sun.data.color = (1.0, 0.89, 0.77)
    world = bpy.data.worlds.new("Richmond daylight")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.43, 0.54, 0.68, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.35

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 820
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.render.render(write_still=True)
    print(f"PASS: Rendered {len(objects)} mesh objects from {mesh_path.name}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--station-bundle", type=Path)
    parser.add_argument("--station-alignment", type=Path)
    parser.add_argument("--save-blend", type=Path)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    options = parser.parse_args(arguments)
    if options.output.suffix.lower() != ".png":
        parser.error("Use a .png output path.")
    if bool(options.station_bundle) != bool(options.station_alignment):
        parser.error("Supply both --station-bundle and --station-alignment.")
    if options.save_blend and options.save_blend.suffix.lower() != ".blend":
        parser.error("Use a .blend path with --save-blend.")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    make_view(options.mesh.resolve(), options.output.resolve(), options.station_bundle, options.station_alignment,
              options.save_blend.resolve() if options.save_blend else None)


if __name__ == "__main__":
    main()
