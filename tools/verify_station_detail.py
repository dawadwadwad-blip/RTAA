"""Verify the saved station scene and the exported glTF asset with Blender."""

import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from station_headhouse import ARCADE, WIDTH


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_glb(path):
    with path.open("rb") as stream:
        magic, version, size, length, kind = struct.unpack("<4sIII4s", stream.read(20))
        require((magic, version, size, kind) == (b"glTF", 2, path.stat().st_size, b"JSON"),
                "Expected a complete glTF 2 binary container.")
        return json.loads(stream.read(length))


def verify(glb):
    scene = bpy.context.scene
    collection = scene.collection.children["Main Street Station | street detail"]
    objects = list(collection.objects)
    require(len(objects) == 5 and all(obj.type == "MESH" for obj in objects), "Expected five station assemblies.")
    require(scene.objects.get("Main Street Station — landmark") is None
            and scene.objects.get("Building_osm_way_113030476") is None, "A legacy headhouse is still visible.")
    require(scene.objects.get("Main Street Station — archived train shed") is not None, "The archive shed is missing.")
    frame = objects[0].matrix_world
    require(all(obj.matrix_world == frame for obj in objects), "Station assemblies do not share a placement frame.")

    main = collection.objects["MSS Headhouse"]
    tree = BVHTree.FromObject(main, bpy.context.evaluated_depsgraph_get())
    for x in ARCADE:
        for z in (1.5, 6.3):
            opening = tree.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)))[0]
            jamb = tree.ray_cast(Vector((x + 1.88, -2.0, z)), Vector((0, 1, 0)))[0]
            require(opening is not None and opening.y > 0.35 and jamb is not None and jamb.y < 0.1,
                    f"Arcade opening at x={x:.2f}, z={z:.2f} is missing a recess or jamb.")
    print("PASS: Both five-bay arcades have real recesses and solid jambs.")

    data = read_glb(glb)
    record = json.loads(glb.with_suffix(".json").read_text(encoding="utf-8"))
    require(all(abs(exported - saved) < 0.0001
                for file_row, scene_row in zip(record["headhouse_xyz_m_to_pilot_east_north_up_m"], frame, strict=True)
                for exported, saved in zip(file_row, scene_row, strict=True)),
            "GLB placement metadata and the Blender scene disagree.")
    require(record["reference_headhouse_width_m"] == WIDTH, "Unexpected reference width.")
    require(record["objects"] == len(data["meshes"]) == len(objects), "glTF object count mismatch.")
    require(0 < record["triangles"] < 65_000, "The close LOD mesh exceeded its triangle check.")
    images = data.get("images", [])
    require(len(images) == 8 and all("bufferView" in img and "uri" not in img for img in images),
            "The four generated material pairs must be embedded.")
    for mesh in data["meshes"]:
        for surface in mesh["primitives"]:
            material = data["materials"][surface["material"]]
            if "normalTexture" in material:
                require("TEXCOORD_0" in surface["attributes"] and "TANGENT" in surface["attributes"],
                        f'Textured primitive in {mesh["name"]} lacks its UV or normal tangent data.')
    print("PASS: glTF embeds eight original maps and textured surfaces have UVs and tangents.")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    require("FINISHED" in bpy.ops.import_scene.gltf(filepath=str(glb)), "Blender could not reimport the GLB.")
    imported = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    require(len(imported) == len(data["meshes"]), "The GLB did not round-trip all station assemblies.")
    print(f'PASS: GLB round-tripped through Blender with {len(imported)} meshes and {record["triangles"]:,} triangles.')


if __name__ == "__main__":
    verify(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
