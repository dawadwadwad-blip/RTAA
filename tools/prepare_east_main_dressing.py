"""Bake the existing East Main kit onto the locked Shockoe GIS footprints and terrain."""

import argparse
from collections import defaultdict
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "rva-east-main-dressing/1"
CELL_M = 108


def frontages(data_dir, manifest, chunks, route):
    import numpy as np
    from PIL import Image
    from pyproj import Transformer
    from shapely import STRtree, intersects_xy, orient_polygons
    from shapely.geometry import Point, shape
    from shapely.ops import transform

    from build_rva_3d_blocks import DISTRICTS, Terrain, building_height, chunk_id, facade, footprint_profile
    from fetch_rva_gis import PROJECTION, load_json, parts_of, sha256

    buildings = data_dir / "rva_buildings.geojson"
    heightmap = data_dir / manifest["heightmap"]["png"]
    for path in (buildings, heightmap):
        if sha256(path) != manifest["files_sha256"][path.name]:
            raise ValueError(f"Input differs from the saved GIS capture: {path.name}.")
    with Image.open(heightmap) as image:
        terrain = Terrain(manifest["heightmap"], np.asarray(image), np)
    project = Transformer.from_pipeline(PROJECTION)
    centers = {name: project.transform(*position) for name, position in DISTRICTS.items()}
    ignored = set(chunks["replaced_osm_ids"]) | {row["id"] for row in chunks["rejected"]}
    known_chunks = {entry["id"] for entry in chunks["chunks"]}
    cell_size = chunks["streaming_cell_m"]
    features = load_json(buildings)["features"]
    entries = []
    polygons = []
    for item in features:
        geom = orient_polygons(transform(project.transform, shape(item["geometry"])))
        if geom.is_empty or not geom.is_valid:
            continue
        parts = list(parts_of(geom, "Polygon"))
        polygons.extend(parts)
        entries.append((item, geom, parts))
    occluders = STRtree(polygons)
    origin = np.add(manifest["origin_grid_m_en"], route["origin_en"])
    tx, tz = route["eastbound_xz"]
    east = np.array([tx, -tz])
    left = np.array([tz, tx])
    stations, offsets = np.asarray(route["east_main_centerline"]).T
    intersections = [s for s, _ in route["intersections"].values()]
    result = []
    for item, geometry, parts in entries:
        source = item["id"]
        tags = item["properties"]["tags"]
        if (source in ignored or facade(tags) != "M_Facade_Brick"
                or tags.get("historic") or tags.get("building") in {"house", "church", "garage", "shed"}):
            continue
        center = geometry.representative_point()
        delta = np.array([center.x, center.y]) - origin
        if not (62 < east @ delta < 555 and abs(left @ delta) < 44):
            continue
        district = min(centers, key=lambda name: math.dist((center.x, center.y), centers[name]))
        cx, cy = (math.floor((point - zero) / cell_size)
                  for point, zero in zip((center.x, center.y), manifest["origin_grid_m_en"], strict=True))
        cell = chunk_id(district, cx, cy)
        if cell not in known_chunks:
            raise ValueError(f"Building {source} has no matching GIS chunk.")
        height, _ = building_height(tags, district, geometry.area)
        for polygon in parts:
            grade, profiles = footprint_profile(polygon, terrain, intersects_xy)
            top = grade + height - manifest["origin_elevation_m"]
            for a, b, samples in profiles[0]:
                vector = np.subtract(b, a)
                length = math.hypot(*vector)
                if length < 3.6:
                    continue
                normal = np.array([vector[1], -vector[0]]) / length
                middle = (np.asarray(a) + b) * 0.5
                relative = middle - origin
                s = float(east @ relative)
                lateral = (left @ relative) + np.interp(s, stations, offsets)
                if not 64 < s < 555 or not 9.0 < abs(lateral) < 31.0:
                    continue
                road_facing = float(normal @ left) * (-1 if lateral > 0 else 1)
                exposed_corner = min(abs(s - x) for x in intersections) < 16 and abs(road_facing) < 0.5
                if road_facing < 0.52 and not exposed_corner:
                    continue
                if any(occluders.query(Point(np.asarray(a) + vector * p + normal * 0.48), predicate="within").size
                       for p in (0.2, 0.5, 0.8)):
                    continue
                base = min(z for _, z in samples) - manifest["origin_elevation_m"]
                tint = "painted" if lateral < 0 and s > 360 else "rose" if lateral > 0 and s < 147 else "brick"
                local = np.subtract(a, manifest["origin_grid_m_en"])
                midpoint = middle - manifest["origin_grid_m_en"]
                result.append({"osm_id": source, "chunk": cell, "station": s, "tint": tint, "corner": exposed_corner,
                               "origin": [*local, base], "normal": [*normal, 0.0], "length": length,
                               "height": top - base, "probe": [midpoint[0], top - 1.2, -midpoint[1]]})
    if not result:
        raise ValueError("No qualifying East Main brick frontages overlap the saved GIS capture.")
    return result


def bake(plan_path, destination):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    from atomic_output import write_json
    from build_pilot_mesh_preview import Surface
    from export_godot_station import tree
    from godot_corridor_dressing import Corridor
    from pilot_contract import load_json
    from station_headhouse import MeshGroup

    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = load_json(plan_path)
    spec = plan["surface"]
    ground = Surface(np.load(plan_path.with_name("terrain.npy")), spec["bounds"], *spec["spacing"])
    corridor = Corridor(plan["corridor"], ground.height)
    materials = corridor.materials()
    groups = defaultdict(list)
    shells = defaultdict(lambda: MeshGroup(materials))
    records = defaultdict(list)
    supports = defaultdict(set)
    for row in plan["frontages"]:
        cell = int(row["station"] // CELL_M)
        corridor.facade_row(shells[cell], Vector(row["origin"]), Vector(row["normal"]), row["length"],
                            row["height"], row["station"], row["corner"], row["tint"])
        records[cell].append({"osm_id": row["osm_id"], "point": row["probe"],
                              "normal": [row["normal"][0], 0, -row["normal"][1]]})
        supports[cell].add(row["chunk"])
    for cell, shell in shells.items():
        groups[cell].append(shell.object("East Main Storefronts", corridor.collection, Matrix.Identity(4)))
    for obj in corridor.street_details(materials, tree, split=True):
        if obj.name.startswith("Corridor sign "):
            cell = int((corridor.inverse @ obj.location).x // CELL_M)
        else:
            cell = int(obj.name.rsplit("_", 1)[1])
        groups[cell].append(obj)
    layers = []
    for cell, objects in sorted(groups.items()):
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.update()
        name = f"east_main_detail_{cell}"
        path = destination / f"{name}.glb"
        points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
        bounds = [min(p.x for p in points), min(-p.y for p in points), max(p.x for p in points), max(-p.y for p in points)]
        for obj in objects:
            obj.select_set(True)
        if "FINISHED" not in bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                                                       export_tangents=True):
            raise ValueError(f"Blender export failed for {name}.")
        layers.append({"id": name, "bounds_xz": bounds, "frontages": records[cell],
                       "building_chunks": sorted(supports[cell]), "mesh_count": len(objects)})
    write_json(destination / "baked.json", {"layers": layers, "parking": corridor.parking})


def build(data_dir, chunks_path, streets_path, output, blender):
    import numpy as np

    from atomic_output import write_json
    from fetch_rva_gis import load_json, sha256
    from prepare_gis_east_main import read_surface

    snapshot = data_dir / "rva_gis_manifest.json"
    manifest = load_json(snapshot)
    streets = load_json(streets_path)
    chunks = load_json(chunks_path)
    digest = sha256(snapshot)
    if (streets["schema"] != "rva-gis-east-main/1" or streets["snapshot_sha256"] != digest
            or chunks["schema"] != "rva-gis-chunks/1" or chunks["source_manifest_sha256"] != digest):
        raise ValueError("Use East Main surfaces and building chunks generated from this GIS snapshot.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Choose a new dressing output directory: {output}.")
    corridor = load_json(ROOT / "reports/east_main_corridor.json")
    corridor["origin_en"] = streets["route"]["origin_en"]
    route = streets["route"] | {"intersections": corridor["intersections"]}
    rows = frontages(data_dir, manifest, chunks, route)
    terrain = read_surface(data_dir, manifest)
    with tempfile.TemporaryDirectory(prefix=".rva-dressing-", dir=output.parent) as scratch:
        work = Path(scratch)
        stage = work / "layer_package"
        stage.mkdir()
        plan = work / "plan.json"
        np.save(work / "terrain.npy", terrain.elevations)
        write_json(plan, {"corridor": corridor, "frontages": rows,
                          "surface": {"bounds": terrain.bounds, "spacing": terrain.spacing}})
        subprocess.run([blender, "--background", "--factory-startup", "--python-exit-code", "1",
                        "--python", str(Path(__file__).resolve()), "--", str(plan), str(stage)], check=True)
        report = load_json(stage / "baked.json")
        (stage / "baked.json").unlink()
        for layer in report["layers"]:
            layer["sha256"] = sha256(stage / (layer["id"] + ".glb"))
        report.update(schema=SCHEMA, source_manifest_sha256=digest, streets_sha256=sha256(streets_path),
                      chunks_sha256=sha256(chunks_path))
        write_json(stage / "east_main_dressing.json", report)
        shutil.move(str(stage), output)
    print(f"PASS: {len(rows)} wall faces across {len({row['osm_id'] for row in rows})} mapped buildings, "
          f"{len(report['layers'])} streamed batches and {len(report['parking'])} parked vehicles.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("outputs/rva_gis"))
    parser.add_argument("--chunks-manifest", type=Path,
                        default=Path("godot/station_trial/assets/rva_gis/meshes/rva_chunks.json"))
    parser.add_argument("--streets", type=Path, default=Path("outputs/rva_gis_east_main/east_main.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/rva_east_main_dressing"))
    parser.add_argument("--blender", default="blender")
    args = parser.parse_args()
    try:
        build(args.data_dir, args.chunks_manifest, args.streets, args.output.resolve(), args.blender)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"East Main dressing failed. {error}\n")


if __name__ == "__main__":
    if "--" in sys.argv and "--background" in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        bake(*(Path(value) for value in sys.argv[sys.argv.index("--") + 1:]))
    else:
        main()
