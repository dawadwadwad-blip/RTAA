import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from xml.etree import ElementTree

from atomic_output import write_json

try:
    import pyproj
    from pyproj.enums import TransformDirection
except ImportError:
    pyproj = None


ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def unreal_position(grid, east_offset, north_offset, navd88_metres):
    scale = grid["centimeters_per_m"]
    return east_offset * scale, -north_offset * scale, (navd88_metres - grid["origin_navd88_m"]) * scale


def height_code(grid, navd88_metres):
    relative_metres = navd88_metres - grid["origin_navd88_m"]
    code = grid["height_code_zero"] + round(grid["height_codes_per_m"] * relative_metres)
    if not 0 <= code <= 65535:
        raise ValueError(f"Elevation {navd88_metres} m exceeds the Landscape encoding range.")
    return code


def cover_tiles(bounds, span):
    west, south, east, north = bounds
    return [(x, y) for y in range(math.floor(south / span), math.ceil(north / span))
            for x in range(math.floor(west / span), math.ceil(east / span))]


def tile_bounds(x, y, span):
    return [x * span, y * span, (x + 1) * span, (y + 1) * span]


def union_bounds(bounds):
    return [min(b[0] for b in bounds), min(b[1] for b in bounds),
            max(b[2] for b in bounds), max(b[3] for b in bounds)]


def audit_osm_capture(path, controls):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    capture = controls["capture"]
    if digest != capture["sha256"] or path.stat().st_size != capture["bytes"]:
        raise ValueError("OSM capture bytes differ from the locked response.")
    root = ElementTree.parse(path).getroot()
    nodes = {int(node.attrib["id"]): node for node in root.findall("node")}
    ways = {int(way.attrib["id"]): way for way in root.findall("way")}
    for control in controls["intersections"]:
        node = nodes[control["osm_node"]]
        lon_lat = [float(node.attrib[a]) for a in ("lon", "lat")]
        if lon_lat != control["lon_lat"] or int(node.attrib["version"]) != control["node_version"]:
            raise ValueError(f'Control node differs from capture: {control["label"]}')
        for reference in control["incident_ways"]:
            way = ways[reference["id"]]
            members = {int(nd.attrib["ref"]) for nd in way.findall("nd")}
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
            if (control["osm_node"] not in members or int(way.attrib["version"]) != reference["version"]
                    or tags.get("name") != reference["name"] or tags.get("highway") != reference["highway"]):
                raise ValueError(f'Control way differs from capture: {reference["id"]}')


def audit_projection_assets(directory, projection_lock):
    for item in projection_lock["grids"]:
        path = directory / item["filename"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if item["sha256"] != digest or item["bytes"] != path.stat().st_size:
            raise ValueError(f'Projection grid bytes differ from the lock: {path.name}')
    pyproj.network.set_network_enabled(False)
    pyproj.datadir.append_data_dir(directory.resolve())
    for operation in projection_lock["operations"]:
        transform = pyproj.Transformer.from_pipeline(operation["pipeline"])
        observed = transform.transform(*operation["fixture_source_xy"], errcheck=True)
        error = math.dist(observed, operation["fixture_target_en_m"])
        if error > projection_lock["test_tolerance_m"]:
            raise ValueError(f'{operation["source_crs"]} fixture differs by {error:.6f} m.')


def make_contract(grid, controls, source_catalog):
    projection = pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"])
    e0, n0 = projection.transform(*grid["origin_wgs84_lon_lat"], errcheck=True)
    span = grid["tile_span_m"]
    samples = span // grid["sample_spacing_m"] + 1
    bracketing = cover_tiles(grid["core_bounds_local_m"], span)
    tile_rows = [{"id": f"e{x:+d}_n{y:+d}", "index_en": [x, y], "local_bounds_m": tile_bounds(x, y, span)}
                 for x, y in bracketing]
    bounds = union_bounds([tile["local_bounds_m"] for tile in tile_rows])
    halo = grid["acquisition_halo_m"]
    acquisition = [bounds[0] - halo, bounds[1] - halo, bounds[2] + halo, bounds[3] + halo]
    features = []

    def geo_rect(kind, rectangle, **properties):
        w, s, e, n = rectangle
        ring = [(w, s), (e, s), (e, n), (w, n), (w, s)]
        positions = [projection.transform(e0 + de, n0 + dn, direction=TransformDirection.INVERSE, errcheck=True)
                     for de, dn in ring]
        features.append({"type": "Feature", "properties": {"kind": kind, **properties},
                         "geometry": {"type": "Polygon",
                                      "coordinates": [[[round(x, 9), round(y, 9)] for x, y in positions]]}})

    geo_rect("pilot_core", grid["core_bounds_local_m"])
    geo_rect("acquisition_with_halo", acquisition)
    for tile in tile_rows:
        geo_rect("landscape_tile", tile["local_bounds_m"], id=tile["id"])
    audited_controls = []
    for control in controls["intersections"]:
        lon, lat = control["lon_lat"]
        east, north = projection.transform(lon, lat, errcheck=True)
        offsets = [east - e0, north - n0]
        x, y, _ = unreal_position(grid, *offsets, grid["origin_navd88_m"])
        point = {"label": control["label"], "osm_node": control["osm_node"],
                 "grid_metres_en": [round(east, 3), round(north, 3)],
                 "local_metres_en": [round(v, 3) for v in offsets],
                 "unreal_centimeters_xy_only": [round(x, 1), round(y, 1)]}
        audited_controls.append(point)
        features.append({"type": "Feature", "properties": {"kind": "osm_control", **point},
                         "geometry": {"type": "Point", "coordinates": [lon, lat]}})

    nodes = [c["osm_node"] for c in audited_controls]
    core = grid["core_bounds_local_m"]
    control_xy = [c["local_metres_en"] for c in audited_controls]
    cross = 0 if len(control_xy) != 3 else abs(
        (control_xy[1][0] - control_xy[0][0]) * (control_xy[2][1] - control_xy[0][1])
        - (control_xy[1][1] - control_xy[0][1]) * (control_xy[2][0] - control_xy[0][0]))
    first, second = map(tuple, grid["first_adjacent_tiles_en"])

    sources = source_catalog["sources"]
    licensed = all(s["license_url"].startswith("https://") and s["license"] for s in sources)
    checks = {
        "frame uses centimeter scale and flips north": (
            unreal_position(grid, 100, 0, 0) == (10000, 0, 0)
            and unreal_position(grid, 0, 100, 0) == (0, -10000, 0)
            and unreal_position(grid, 0, 0, 1) == (0, 0, 100)),
        "height encoding keeps one metre at 128 codes": height_code(grid, 0) == 32768 and height_code(grid, 1) == 32896,
        "505 landscape samples cover 504 metre cells": samples == 505 and grid["sample_spacing_m"] == 1,
        "first two terrain tiles are adjacent": first in bracketing and second in bracketing
        and sum(abs(a - b) for a, b in zip(first, second)) == 1,
        "three non-collinear OSM controls are within the core": len(set(nodes)) == 3 and cross > 10000
        and all(core[0] < e < core[2] and core[1] < n < core[3] for e, n in control_xy),
        "source catalog has distinct IDs and explicit licenses": len({s["id"] for s in sources}) == len(sources) and licensed,
    }
    manifest = {
        "crs": {"horizontal": grid["horizontal_crs"], "vertical": grid["vertical_crs"]},
        "origin_grid_m_en": [round(e0, 6), round(n0, 6)],
        "origin_navd88_m": grid["origin_navd88_m"],
        "core_local_bounds_m": core,
        "tile_union_local_bounds_m": bounds,
        "acquisition_local_bounds_m": acquisition,
        "acquisition_grid_bounds_m": [round(v + origin, 6) for v, origin in zip(acquisition, [e0, n0, e0, n0])],
        "tile_span_m": span, "sample_spacing_m": grid["sample_spacing_m"],
        "vertices_per_axis": samples, "first_adjacent_tiles_en": grid["first_adjacent_tiles_en"],
        "tiles": tile_rows, "controls": audited_controls,
        "plan_view_control_triangle_area_m2": round(cross / 2, 1),
    }
    coverage = {"type": "FeatureCollection", "attribution": controls["attribution"], "features": features}
    return manifest, coverage, checks


def main():
    parser = argparse.ArgumentParser(description="Validate the Richmond pilot grid and source contract.")
    parser.add_argument("--osm-capture", type=Path, help="Audit the exact raw OSM capture when available.")
    parser.add_argument("--proj-grid-dir", type=Path, help="Verify exact NADCON5 grid files and transformations.")
    args = parser.parse_args()
    if pyproj is None:
        print("Missing pyproj. Install it from requirements-gis.txt.", file=sys.stderr)
        return 3
    try:
        grid = load_json(ROOT / "pilot/grid.json")
        controls = load_json(ROOT / "pilot/controls.json")
        sources = load_json(ROOT / "data/catalog.json")
        manifest, coverage, checks = make_contract(grid, controls, sources)
        if args.osm_capture is not None:
            audit_osm_capture(args.osm_capture, controls)
            checks["locked raw OSM bytes contain the versioned control nodes and ways"] = True
        if args.proj_grid_dir is not None:
            audit_projection_assets(args.proj_grid_dir, load_json(ROOT / "data/projection_lock.json"))
            checks["pinned NADCON5 grids reproduce both NOAA horizontal transforms offline"] = True
        if not all(checks.values()):
            raise ValueError("One or more pilot geometry or source checks failed: " + str(checks))
        write_json(ROOT / "pilot/tile_manifest.json", manifest)
        write_json(ROOT / "pilot/coverage.geojson", coverage)
        write_json(ROOT / "reports/pilot_contract.json", {
            "checks": checks, "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str,
            "control_count": len(manifest["controls"]), "landscape_tile_count": len(manifest["tiles"]),
            "source_asset_status": {s["id"]: s["asset_status"] for s in sources["sources"]},
        })
    except FileNotFoundError as exc:
        print(f"Missing pilot input: {exc.filename}", file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, pyproj.exceptions.ProjError) as exc:
        print(f"Pilot contract validation failed: {exc}", file=sys.stderr)
        return 1
    for name in checks:
        print(f"PASS: {name}")
    print(f'{len(manifest["tiles"])} landscape tiles, {len(manifest["controls"])} control intersections')
    return 0


if __name__ == "__main__":
    sys.exit(main())
