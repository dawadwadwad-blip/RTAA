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
from mathutils.bvhtree import BVHTree


def export_station(objects, frame, output):
    import station_headhouse

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.matrix_world = Matrix.Identity(4)
        obj.select_set(True)
    try:
        if "FINISHED" not in bpy.ops.export_scene.gltf(
                filepath=str(output), export_format="GLB", use_selection=True, export_tangents=True):
            raise RuntimeError("Cannot export the station GLB.")
    finally:
        for obj in objects:
            obj.matrix_world = frame
    for obj in objects:
        obj.data.calc_loop_triangles()
    evidence = {
        "asset": output.name,
        "gltf_axis": "standard glTF Y-up; Blender source Z-up with X along the frontage",
        "headhouse_xyz_m_to_pilot_east_north_up_m": [list(row) for row in frame],
        "reference_headhouse_width_m": station_headhouse.WIDTH,
        "objects": len(objects),
        "triangles": sum(len(obj.data.loop_triangles) for obj in objects),
        "material_images": sorted(img.name for img in bpy.data.images if img.name.startswith("MSS ")),
    }
    output.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f'PASS: Exported the station exterior and train shed with {evidence["triangles"]:,} triangles.')


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
    return plan, station


def insert_decks(directory, mesh_report):
    report = json.loads((directory / "station_decks.json").read_text(encoding="utf-8"))
    if (report.get("schema_version") != 1 or report.get("mode") != "local_lidar_to_dem_visual_preview"
            or report["terrain_report_sha256"] != mesh_report["terrain_report_sha256"]):
        raise ValueError("The station deck preview uses a different terrain export.")
    geometry = report["geometry"]
    if geometry["mesh"] != "RVA_Station_Decks.obj" or geometry["material"] != "RVA_Station_Decks.mtl":
        raise ValueError("Unexpected viaduct package filenames.")
    for name, sha in ((geometry["mesh"], geometry["sha256"]), (geometry["material"], geometry["material_sha256"])):
        with (directory / name).open("rb") as asset:
            if hashlib.file_digest(asset, "sha256").hexdigest() != sha:
                raise ValueError(f"Station deck file {name} differs from its report.")
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(filepath=str(directory / geometry["mesh"]), forward_axis="Y", up_axis="Z")
    imported = {obj.name for obj in bpy.context.scene.objects if obj not in before}
    expected = {profile["name"] + "_Surface" for profile in report["profiles"]}
    if not expected.issubset(imported):
        raise ValueError("Blender did not import every station deck surface.")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for profile in report["profiles"]:
        obj = bpy.context.scene.objects[profile["name"] + "_Surface"]
        crossing = profile["east_main"]
        x, y = crossing["local_en_m"]
        origin = obj.matrix_world.inverted() @ Vector((x, y, crossing["deck_z_m_in_preview"] + 3))
        direction = obj.matrix_world.inverted().to_3x3() @ Vector((0, 0, -1))
        hit = BVHTree.FromObject(obj, depsgraph).ray_cast(origin, direction)[0]
        # A railhead may be present in a slanted center-ray at a curved crossing.
        limit = 0.16 if profile["kind"] == "rail" else 0.065
        if hit is None or abs((obj.matrix_world @ hit).z - crossing["deck_z_m_in_preview"]) > limit:
            raise ValueError(f"Imported crossing height differs from the profile for {profile['name']}.")
    print(f"PASS: Imported {len(expected)} elevated surfaces and checked their East Main Street crossing heights.")


def make_view(mesh_path, output, bundle=None, alignment=None, blend=None, *,
              station_view=None, station_glb=None, station_decks=None, samples=32, resolution=100, build_only=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    mesh_report = json.loads((mesh_path.parent / "pilot_mesh_preview.json").read_text(encoding="utf-8"))
    with mesh_path.open("rb") as mesh:
        if hashlib.file_digest(mesh, "sha256").hexdigest() != mesh_report["mesh_sha256"]:
            raise ValueError("The preview OBJ differs from its report.")
    bpy.ops.wm.obj_import(filepath=str(mesh_path), forward_axis="Y", up_axis="Z")
    if station_decks:
        insert_decks(station_decks, mesh_report)

    plan, station = insert_station(scene, bundle, alignment, mesh_report) if bundle else (None, None)
    if station_view:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from station_headhouse import replace_station

        station_frame, detail_objects = replace_station(scene, station)
        if station_glb:
            export_station(detail_objects, station_frame, station_glb)

    objects = [obj for obj in scene.objects if obj.type == "MESH"]
    terrain = next(obj for obj in objects if obj.name == "Terrain")
    points = [terrain.matrix_world @ Vector(corner) for corner in terrain.bound_box]
    west, east = min(p.x for p in points), max(p.x for p in points)
    south, north = min(p.y for p in points), max(p.y for p in points)
    center = Vector(((west + east) / 2 + 15, (south + north) / 2, 6))
    if any(abs(a - b) > 0.02 for a, b in zip(
            (west, south, east, north), mesh_report["bounds_local_en_m"])):
        raise ValueError("The imported axes and terrain bounds differ from the mesh report.")

    station_cameras = {
        "street": ((26, -54, -0.87), (14.9, 0.25, 13.3), 38),
        "entrance": ((25.3, -13.6, -0.88), (14.35, 0.4, 6.75), 25),
        "rail": ((-67, 64, 1.20), (1.2, 31.4, 13.6), 32),
        "decks": ((130, -34, 63), (-12.0, 38.0, 4.2), 32),
    }
    if station_view:
        station_eye, station_target, lens = station_cameras[station_view]
        if station_decks and station_view == "street":
            station_eye = (38, -54, -0.87)
        eye = station_frame @ Vector(station_eye)
        target = station_frame @ Vector(station_target)
    elif plan:
        eye = Vector((*plan["camera_eye_en_m"], plan["camera_eye_height_m"]))
        target = Vector((*plan["clock_anchor_en_m"], plan["clock_anchor_dem_m"] + 14))
    else:
        eye, target = center + Vector((440, -710, 720)), center
    bpy.ops.object.camera_add(location=eye)
    camera = bpy.context.object
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    if station_view:
        camera.data.lens = lens
    elif plan:
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
    if station_view:
        light_direction = (0.60, 0.34, -0.73) if station_view == "rail" else (-0.24, 0.58, -0.75)
        sun.rotation_euler = (station_frame.to_3x3() @ Vector(light_direction)).to_track_quat("-Z", "Y").to_euler()
        sun.data.energy = 2.45
        sun.data.angle = 0.055
        sun.data.color = (1.0, 0.91, 0.79)
        # Light with a quiet overcast fill and show a gradient sky to the camera.
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        background = nodes["Background"]
        rays = nodes.new("ShaderNodeLightPath")
        mix = nodes.new("ShaderNodeMixShader")
        sky = nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_disc = False
        sky.sun_elevation = 0.85
        sky.air_density = 1.12
        visible = nodes.new("ShaderNodeBackground")
        visible.inputs["Strength"].default_value = 0.31
        links.new(sky.outputs["Color"], visible.inputs["Color"])
        links.new(rays.outputs["Is Camera Ray"], mix.inputs[0])
        links.new(background.outputs[0], mix.inputs[1])
        links.new(visible.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], nodes["World Output"].inputs["Surface"])
        background.inputs["Strength"].default_value = 0.51

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 1600 if station_view else 1400
    scene.render.resolution_y = (1000 if station_view in {"rail", "decks"} else 1300) if station_view else 820
    scene.render.resolution_percentage = resolution
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    if not build_only:
        bpy.ops.render.render(write_still=True)
        print(f"PASS: Rendered {len(objects)} mesh objects from {mesh_path.name}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--station-bundle", type=Path)
    parser.add_argument("--station-alignment", type=Path)
    parser.add_argument("--save-blend", type=Path)
    parser.add_argument("--station-view", choices=("street", "entrance", "rail", "decks"))
    parser.add_argument("--station-glb", type=Path)
    parser.add_argument("--station-decks", type=Path, help="Include a built station deck preview directory.")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--resolution", type=int, default=100, help="Render resolution percentage.")
    parser.add_argument("--build-only", action="store_true", help="Build the requested scene or GLB without rendering.")
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    options = parser.parse_args(arguments)
    if options.output.suffix.lower() != ".png":
        parser.error("Use a .png output path.")
    if bool(options.station_bundle) != bool(options.station_alignment):
        parser.error("Supply both --station-bundle and --station-alignment.")
    if options.save_blend and options.save_blend.suffix.lower() != ".blend":
        parser.error("Use a .blend path with --save-blend.")
    if options.station_view and not options.station_bundle:
        parser.error("--station-view requires --station-bundle and --station-alignment.")
    if options.station_view == "decks" and not options.station_decks:
        parser.error("The decks view requires --station-decks.")
    if options.station_glb and (not options.station_view or options.station_glb.suffix.lower() != ".glb"):
        parser.error("--station-glb requires a .glb path and --station-view.")
    if options.samples < 1 or not 1 <= options.resolution <= 100:
        parser.error("Use positive samples and a resolution from 1 to 100 percent.")
    if options.build_only and not (options.save_blend or options.station_glb):
        parser.error("--build-only requires --save-blend or --station-glb.")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    make_view(options.mesh.resolve(), options.output.resolve(), options.station_bundle, options.station_alignment,
              options.save_blend.resolve() if options.save_blend else None, station_view=options.station_view,
              station_glb=options.station_glb.resolve() if options.station_glb else None,
              station_decks=options.station_decks.resolve() if options.station_decks else None,
              samples=options.samples, resolution=options.resolution, build_only=options.build_only)


if __name__ == "__main__":
    main()
