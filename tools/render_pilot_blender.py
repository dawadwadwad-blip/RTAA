"""Render the assembled Richmond mesh with Blender's built-in Cycles renderer."""

import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def make_view(mesh_path, output):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    bpy.ops.wm.obj_import(filepath=str(mesh_path), forward_axis="NEGATIVE_Y", up_axis="Z")

    objects = [obj for obj in scene.objects if obj.type == "MESH"]
    terrain = next(obj for obj in objects if obj.name == "Terrain")
    points = [terrain.matrix_world @ Vector(corner) for corner in terrain.bound_box]
    west, east = min(p.x for p in points), max(p.x for p in points)
    south, north = min(p.y for p in points), max(p.y for p in points)
    center = Vector(((west + east) / 2 + 15, (south + north) / 2, 6))
    if east - west < 1000 or north - south < 500:
        raise ValueError("The imported terrain frame was smaller than the western pair.")

    bpy.ops.object.camera_add(location=center + Vector((440, -710, 720)))
    camera = bpy.context.object
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
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
    bpy.ops.render.render(write_still=True)
    print(f"PASS: Rendered {len(objects)} mesh objects from {mesh_path.name}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh", type=Path)
    parser.add_argument("output", type=Path)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    options = parser.parse_args(arguments)
    if options.output.suffix.lower() != ".png":
        parser.error("Use a .png output path.")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    make_view(options.mesh.resolve(), options.output.resolve())


if __name__ == "__main__":
    main()
