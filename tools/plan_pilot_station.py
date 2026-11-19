"""Fit the archived Main Street Station mesh to the current Richmond pilot."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile

from atomic_output import write_json
from build_pilot_mesh_preview import digest, load_surface, scale, shape, shapely
from pilot_contract import ROOT, load_json, pyproj

try:
    from shapely.geometry import Polygon
except ImportError:
    Polygon = None


PREFIX = "Richmond_Unreal_First_Drive/"
MESH_MEMBER = PREFIX + "Meshes/RVA_Main_Street_Station.fbx"
FOOTPRINT = "osm/way/113030476"
METRES_PER_LATITUDE_DEGREE = 111195.0


def projector(grid):
    projection = pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"])
    lon, lat = grid["origin_wgs84_lon_lat"]
    e0, n0 = projection.transform(lon, lat, errcheck=True)
    longitude_scale = METRES_PER_LATITUDE_DEGREE * math.cos(math.radians(lat))

    def project(east, north):
        e, n = projection.transform(lon + east / longitude_scale, lat + north / METRES_PER_LATITUDE_DEGREE,
                                    errcheck=True)
        return e - e0, n - n0

    return project


def affine_around(project, spawn, clock_legacy):
    clock_east, clock_north = clock_legacy
    e, n = project(clock_east, clock_north)
    e_dx, n_dx = project(clock_east + 1, clock_north)
    e_dy, n_dy = project(clock_east, clock_north + 1)
    dx, dy = clock_east - spawn[0], clock_north - spawn[1]
    a, b, c, d = e_dx - e, e_dy - e, n_dx - n, n_dy - n
    return [[a, b, e - a * dx - b * dy], [c, d, n - c * dx - d * dy]], (dx, dy), (e, n)


def plan(bundle, buildings_path, terrain, output):
    grid = load_json(ROOT / "pilot/grid.json")
    manifest = load_json(ROOT / "pilot/tile_manifest.json")
    bundle_sha = digest(bundle)
    if bundle_sha != load_json(ROOT / "reports/baseline.json")["bundle"]["sha256"]:
        raise ValueError("The supplied first-drive ZIP differs from the audited archive.")
    surface = load_surface(terrain, grid, manifest)
    buildings = load_json(buildings_path)
    report_hash = load_json(ROOT / "reports/pilot_building_heights.json")["export_sha256"]
    if digest(buildings_path) != report_hash:
        raise ValueError("The station footprint must come from the audited building export.")
    current = next(row for row in buildings["footprints"] if row["id"] == FOOTPRINT)
    target = scale(shape(current["footprint_unreal_xy_cm"]), xfact=0.01, yfact=-0.01, origin=(0, 0))

    with ZipFile(bundle) as archive:
        site = json.loads(archive.read(PREFIX + "Site_Reference.json"))
        old = json.loads(archive.read(PREFIX + "Richmond_OpenStreetMap_ODbL.json"))
        geometry = hashlib.sha256(archive.read(MESH_MEMBER)).hexdigest()
    if site["originWGS84"] != grid["origin_wgs84_lon_lat"] or old["origin"] != site["originWGS84"]:
        raise ValueError("The archived station uses a different map origin.")
    found = next(key for key, value in site["architecture"].items() if value.get("name") == "Main Street Station and trainshed")
    boundary = old["buildings"][int(found)][5]
    vertices = list(zip(boundary[::2], boundary[1::2]))
    project = projector(grid)
    outline = Polygon([project(x, y) for x, y in vertices])
    overlap = outline.intersection(target).area / outline.union(target).area
    clock = next(part for part in site["landmarkParts"] if part["name"] == "Main Street Station clock tower")
    spawn = site["spawnRelativeToMapMetres"]
    affine, legacy_clock, clock_anchor = affine_around(project, spawn, (clock["x"], clock["z"]))
    residuals = [
        math.dist(project(x, y), tuple(row[0] * (x - spawn[0]) + row[1] * (y - spawn[1]) + row[2] for row in affine))
        for x, y in vertices
    ]
    if overlap < 0.95 or max(residuals) > 0.10:
        raise ValueError(f"Legacy station alignment failed. Overlap {overlap:.4f}, max affine residual {max(residuals):.3f} m.")

    camera = (-750.0, 338.0)
    result = {
        "schema_version": 1, "archive_sha256": bundle_sha, "asset_member": MESH_MEMBER, "asset_sha256": geometry,
        "replacement_object": "Building_" + FOOTPRINT.replace("/", "_"), "footprint_id": FOOTPRINT,
        "legacy_mesh_xy_to_pilot_en": affine, "legacy_clock_xy_m": legacy_clock, "clock_anchor_en_m": clock_anchor,
        "clock_anchor_dem_m": float(surface.height(*clock_anchor)), "xy_intersection_over_union": round(overlap, 6),
        "maximum_affine_residual_m": round(max(residuals), 6), "height_reference": "preview_dem",
        "camera_eye_en_m": camera, "camera_eye_height_m": float(surface.height(*camera) + 1.8),
        "terrain_report_sha256": digest(terrain / "terrain_first_pair.json"),
        "footprint_export_sha256": report_hash, "osm_attribution": buildings["osm_attribution"],
    }
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "inputs/Richmond_Unreal_First_Drive.zip")
    parser.add_argument("--buildings", type=Path, default=ROOT / "outputs/pilot_building_heights.json")
    parser.add_argument("--terrain", type=Path, default=ROOT / "outputs/terrain-first-pair-dem-preview")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/pilot_station_alignment.json")
    args = parser.parse_args()
    if shapely is None or pyproj is None:
        print("BLOCKED: Install requirements-gis.txt before planning the landmark.", file=sys.stderr)
        return 3
    try:
        if args.output.resolve() in {args.bundle.resolve(), args.buildings.resolve()} or (
                args.output.resolve().is_relative_to(args.terrain.resolve())):
            raise ValueError("The station plan must have its own output path.")
        report = plan(args.bundle, args.buildings, args.terrain, args.output)
    except FileNotFoundError as error:
        print(f"BLOCKED: Missing input {error.filename}.", file=sys.stderr)
        return 3
    except (BadZipFile, KeyError, OSError, StopIteration, ValueError, pyproj.exceptions.ProjError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f'PASS: Legacy and current station outlines have {report["xy_intersection_over_union"]:.4%} intersection over union.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
