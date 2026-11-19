"""Verify the saved station scene and the exported glTF asset with Blender."""

import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from station_headhouse import ARCADE, BAY, EAVE, STAIR_LEFT, STAIR_RIGHT, WIDTH


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
    require(len(objects) == 6 and all(obj.type == "MESH" for obj in objects), "Expected six station assemblies.")
    require(scene.objects.get("Main Street Station — landmark") is None
            and scene.objects.get("Building_osm_way_113030476") is None, "A legacy headhouse is still visible.")
    require(scene.objects.get("Main Street Station — archived train shed") is None
            and collection.objects.get("MSS Restored train shed") is not None, "Expected only the rebuilt train shed.")
    frame = objects[0].matrix_world
    require(all(obj.matrix_world == frame for obj in objects), "Station assemblies do not share a placement frame.")

    main = collection.objects["MSS Headhouse"]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(main, depsgraph)
    for x in ARCADE:
        for z, min_depth in ((1.45, 1.40), (6.1, 2.9)):
            opening = tree.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)))[0]
            jamb = tree.ray_cast(Vector((x + BAY / 2 - 0.07, -2.0, z)), Vector((0, 1, 0)))[0]
            require(opening is not None and opening.y > min_depth and jamb is not None and jamb.y < 0.1,
                    f"Arcade opening at x={x:.2f}, z={z:.2f} is missing a recess or jamb.")
    passage = tree.ray_cast(Vector((ARCADE[0], 1.30, 6.1)), Vector((1, 0, 0)))[0]
    require(passage is not None and passage.x > ARCADE[-1], "The loggia is not continuous behind the five arches.")

    stair_tree = BVHTree.FromObject(collection.objects["MSS Main Street forecourt"], depsgraph)
    for x in (STAIR_LEFT + 0.48, (STAIR_LEFT + STAIR_RIGHT) / 2 + 1.0, STAIR_RIGHT - 0.47):
        step = stair_tree.ray_cast(Vector((x, -9.32, 2.0)), Vector((0, 0, -1)))[0]
        require(step is not None and -2.20 < step.z < -1.80, "Missing wide entrance step.")
    tower = collection.objects["MSS Clock tower"]
    roof = BVHTree.FromObject(tower, depsgraph).ray_cast(Vector((4.0, 4.4, 33)), Vector((0, 0, -1)))
    require(roof[0] is not None and roof[0].z > 28
            and tower.data.materials[tower.data.polygons[roof[2]].material_index].name == "MSS Red clay roof tile",
            "Expected a clay-tiled dome over the tower.")
    roof_tree = BVHTree.FromObject(collection.objects["MSS Red clay hip and dormers"], depsgraph)
    eave = roof_tree.ray_cast(Vector((3.0, -2.0, EAVE + 0.02)), Vector((0, 1, 0)), 2.0)[0]
    require(eave is None, "The headhouse roof protrudes across the face of the clock tower.")
    print("PASS: Recessed arcades, continuous 3 m loggia, wide stairs, and a clay dome above an unobstructed tower.")

    data = read_glb(glb)
    record = json.loads(glb.with_suffix(".json").read_text(encoding="utf-8"))
    require(all(abs(exported - saved) < 0.0001
                for file_row, scene_row in zip(record["headhouse_xyz_m_to_pilot_east_north_up_m"], frame, strict=True)
                for exported, saved in zip(file_row, scene_row, strict=True)),
            "GLB placement metadata and the Blender scene disagree.")
    require(record["reference_headhouse_width_m"] == WIDTH, "Unexpected reference width.")
    require(record["objects"] == len(data["meshes"]) == len(objects), "glTF object count mismatch.")
    require(0 < record["triangles"] < 95_000, "The combined close-view asset exceeded its triangle check.")
    images = data.get("images", [])
    require(len(images) == 8 and all("bufferView" in img and "uri" not in img for img in images),
            "The four generated material pairs must be embedded.")
    glazing = next(mat for mat in data["materials"] if mat["name"] == "MSS Train shed glazing")
    require(glazing.get("alphaMode") == "BLEND" and glazing["pbrMetallicRoughness"]["baseColorFactor"][3] < 0.5,
            "The train shed exported as opaque glazing.")
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
