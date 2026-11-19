"""Package the approved station scene for the isolated Unreal collision map."""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic_output import write_json
from station_smoke_contract import (AXES, APPROACH_ROAD, DECKS, FORECOURT, LEGACY_ROAD, MESHES, digest_file,
                                    json_bytes, mesh_bounds, read_bundle, sha, ue_position)


ROOT = Path(__file__).resolve().parents[1]
# Keep the terrain beneath the station and its East Main Street test route.
TERRAIN_CROP = (-840, 236, -596, 442)
DOWN = Vector((0, 0, -1))


def extract(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    world = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    coordinates = [ue_position(point) for point in world]
    vertices, triangles, seen, directed, remap = [], [], set(), set(), {}
    discarded = 0
    for triangle in mesh.loop_triangles:
        a, b, c = triangle.vertices
        points = [world[i] for i in (a, b, c)]
        if obj.name in ("Terrain", LEGACY_ROAD):
            w, s, e, n = TERRAIN_CROP
            if (max(p.x for p in points) < w or min(p.x for p in points) > e
                    or max(p.y for p in points) < s or min(p.y for p in points) > n):
                continue
        p, q, r = (Vector(coordinates[i]) for i in (a, b, c))
        if (q - p).cross(r - p).length_squared < 1e-12:
            discarded += 1
            continue
        # Reflecting Y changes orientation. Reverse once to retain the source surface normals.
        order = (a, c, b)
        indices = []
        for source in order:
            if source not in remap:
                remap[source] = len(vertices)
                vertices.append(coordinates[source])
            indices.append(remap[source])
        edges = list(zip(indices, indices[1:] + indices[:1]))
        # Preserve nonmanifold authored faces without asking DynamicMesh to share overused edges.
        key = frozenset(indices)
        if key in seen or any(edge in directed for edge in edges):
            indices = list(range(len(vertices), len(vertices) + 3))
            vertices.extend(coordinates[source] for source in order)
        else:
            seen.add(key)
            directed.update(edges)
        triangles.append(indices)
    if not triangles:
        raise ValueError(f"No triangles were exported from {obj.name}.")
    vectors = [Vector(vertex) for vertex in vertices]
    tree = BVHTree.FromPolygons(vectors, triangles, all_triangles=True)
    return {"vertices": vertices, "triangles": triangles}, tree, discarded


def measured_probes(objects, trees, frame, approach, decks):
    source_trees = {}
    probes = []
    deps = bpy.context.evaluated_depsgraph_get()

    def measure(name, source, point, tolerance=0.035):
        inverse = objects[source].matrix_world.inverted()
        if source not in source_trees:
            source_trees[source] = BVHTree.FromObject(objects[source], deps)
        east, north, expected = point
        above = Vector((east, north, expected + 0.20))
        hit = source_trees[source].ray_cast(inverse @ above, inverse.to_3x3() @ DOWN, 0.5)[0]
        if hit is None:
            raise ValueError(f"Source mesh {source} is missing level {name}.")
        z = (objects[source].matrix_world @ hit).z
        if abs(z - expected) > tolerance:
            raise ValueError(f"{name} differs by {abs(z - expected):.3f} m from the locked height.")
        xyz = ue_position((east, north, z))
        placed = trees[source].ray_cast(Vector((xyz[0], xyz[1], xyz[2] + 20)), DOWN, 50)[0]
        if placed is None or abs(placed.z - xyz[2]) > 0.02:
            raise ValueError(f"The converted geometry does not reproduce {name} within 0.2 mm.")
        probes.append({"name": name, "mesh": MESHES[source], "point_cm": xyz})
        return z

    for witness in approach["witnesses"]:
        measure(witness["name"], witness["object"], (*witness["local_en_m"], witness["z_m"]))
    for index in range(15):
        y = -10.365 + 0.283 * index + 0.134
        z = -2.58 + 0.200 * index
        measure(f"stair_tread_{index + 1:02d}", FORECOURT, frame @ Vector((16, y, z)), 0.002)
    join_gaps = {}
    joins = approach["road_joins"]
    for side in ("west", "east"):
        heights = []
        for suffix, expected_object in (("inside", APPROACH_ROAD), ("outside", LEGACY_ROAD)):
            name = f"{side}_join_{suffix}"
            row, = (row for row in joins if row["name"] == name and row["object"] == expected_object)
            heights.append(measure(name, expected_object, (*row["local_en_m"], row["z_m"])))
        join_gaps[side] = round(abs(heights[0] - heights[1]) * 100, 3)
        if join_gaps[side] > 5:
            raise ValueError(f"The {side} road join changes height by more than 5 cm across 50 cm.")
    profiles = {profile["name"]: profile["east_main"] for profile in decks["profiles"]}
    for name in DECKS:
        row = profiles[name]
        east, north = row["local_en_m"]
        ground = measure(f"ground_below_{name}", "Terrain", (east, north, row["ground_z_m_in_preview"]))
        deck = measure(f"crossing_{name}", name + "_Surface", (east, north, row["deck_z_m_in_preview"]),
                       0.16 if name == "Bellwood_Rail_Trestle" else 0.065)
        if deck - ground < 6:
            raise ValueError(f"The {name} layer is too close to its ground reference.")
    return probes, join_gaps


def export(bundle, report_path, approach_path, deck_path, frame_path):
    approach, decks, sidecar = (json.loads(path.read_text(encoding="utf-8"))
                                for path in (approach_path, deck_path, frame_path))
    if approach["terrain_report_sha256"] != decks["terrain_report_sha256"]:
        raise ValueError("The approach and viaducts must share the same preview terrain.")
    objects = {name: bpy.context.scene.objects[name] for name in MESHES}
    frame = objects["MSS Headhouse"].matrix_world
    for expected in (approach["station_frame"], sidecar["headhouse_xyz_m_to_pilot_east_north_up_m"]):
        if any(abs(a - b) > 0.001 for row, target in zip(frame, expected, strict=True)
               for a, b in zip(row, target, strict=True)):
            raise ValueError("The saved station placement differs from the approach or GLB sidecar.")
    metadata, payloads, trees = {}, {}, {}
    for name, key in MESHES.items():
        mesh, trees[name], discarded = extract(objects[name])
        raw = json_bytes(mesh)
        metadata[key] = {"source": name, "sha256": sha(raw), "triangles": len(mesh["triangles"]),
                         "bounds_cm": mesh_bounds(mesh["vertices"]), "collapsed_faces_omitted": discarded}
        payloads[key] = raw
    probes, join_gaps = measured_probes(objects, trees, frame, approach, decks)
    manifest = {"version": 1, "axes": AXES, "meshes": metadata, "probes": probes,
                "road_join_height_change_cm_across_50_cm": join_gaps, "attribution": approach["attribution"],
                "terrain_crop_local_en_m": TERRAIN_CROP, "approach_mesh_sha256": approach["mesh_sha256"],
                "viaduct_mesh_sha256": decks["geometry"]["sha256"], "frame_sidecar_sha256": digest_file(frame_path)}
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=bundle.parent) as staging:
        staged = Path(staging) / bundle.name
        with ZipFile(staged, "w", compression=ZIP_DEFLATED, compresslevel=6) as output:
            # Fixed ZIP member times make repeated builds byte-identical.
            for key, raw in [("manifest", json_bytes(manifest)), *payloads.items()]:
                output.writestr(ZipInfo(f"{key}.json"), raw, compress_type=ZIP_DEFLATED, compresslevel=6)
        read_bundle(staged)
        staged.replace(bundle)
    write_json(report_path, {**manifest, "package_sha256": digest_file(bundle)})
    print(f"PASS: Packaged {len(metadata)} station meshes and verified {len(probes)} source and converted heights.")
    print(f"PASS: Road join height changes across 50 cm: west {join_gaps['west']:.2f} cm, east {join_gaps['east']:.2f} cm.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True, help="JSON sidecar of the matching station GLB")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/station-smoke/RVA_Station_Smoke.zip")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/station_smoke_package.json")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    export(args.output, args.report, ROOT / "reports/station_approach.json", ROOT / "reports/station_decks.json", args.frame)


if __name__ == "__main__":
    main()
