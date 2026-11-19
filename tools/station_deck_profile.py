"""Fit preview-only deck profiles near Richmond Main Street Station."""

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import sys
from xml.etree import ElementTree

from atomic_output import write_json
from build_pilot_mesh_preview import digest, load_surface
from pilot_contract import ROOT, audit_osm_capture, audit_projection_assets, load_json, pyproj
from pilot_street_graph import node_rows, tags
from terrain_first_pair import assert_compound_crs, verify_asset

try:
    import laspy
    import numpy as np
    from scipy.spatial import cKDTree
    from shapely.geometry import LineString, box
except ImportError:
    laspy = None


MODE = "local_lidar_to_dem_visual_preview"
SOURCE_EXTENT = (-825, 195, -610, 494)
FIT_EXTENT = (-808, 226, -630, 461)
STEP_M = 5.0
RADIUS_M = 2.4
MAIN_STREET_OSM = 1366154365


@dataclass(frozen=True)
class Corridor:
    name: str
    ways: tuple[int, ...]
    kind: str
    layer: int
    width: float
    bounds: tuple[float, float, float, float]
    lidar_band: tuple[float, float]
    max_gap: float
    max_grade: float


CORRIDORS = (
    Corridor("I95_West_Mainline", (601107599, 38232910), "road", 3, 11.5, (-785, 242, -682, 445), (18, 33), 12, 0.085),
    Corridor("I95_East_Mainline", (45088311,), "road", 3, 10.5, (-785, 242, -682, 445), (18, 33), 12, 0.085),
    Corridor("I95_East_Ramp", (175298408,), "ramp", 3, 5.0, (-785, 242, -682, 445), (18, 32), 12, 0.085),
    Corridor("Bellwood_Rail_Trestle", (38232584,), "rail", 1, 6.4, (-815, 230, -680, 348), (10.5, 16.2), 88, 0.026),
)


def read_cloud(source_dir, source_lock, transform, origin):
    dx, dy = origin
    w, s, e, n = SOURCE_EXTENT
    rw, rs, re, rn = transform.transform_bounds(
        w + dx, s + dy, e + dx, n + dy, densify_pts=21, direction="INVERSE")
    collected = {2: [], 17: []}
    source_tiles = []
    for item in source_lock["assets"]:
        if item["kind"] != "laz":
            continue
        path = source_dir / item["file"]
        if not verify_asset(path, item):
            raise ValueError(f"Point cloud bytes differ from the lock: {path.name}.")
        with laspy.open(path) as reader:
            assert_compound_crs(reader.header.parse_crs(), source_lock["source_reference"]["laz"], path.name)
            low, high = reader.header.mins, reader.header.maxs
            if high[0] < rw or low[0] > re or high[1] < rs or low[1] > rn:
                continue
            source_tiles.append(path.name)
            for chunk in reader.chunk_iterator(300_000):
                x, y, z = map(np.asarray, (chunk.x, chunk.y, chunk.z))
                cls = np.asarray(chunk.classification)
                usable = (~np.asarray(chunk.withheld, dtype=bool) & np.isin(cls, (2, 17))
                          & (x >= rw - 1) & (x <= re + 1) & (y >= rs - 1) & (y <= rn + 1))
                east, north = transform.transform(x[usable], y[usable], errcheck=True)
                east, north = east - dx, north - dy
                cropped = (east >= w) & (east <= e) & (north >= s) & (north <= n)
                for collection in collected:
                    keep = cropped & (cls[usable] == collection)
                    if keep.any():
                        collected[collection].append(np.column_stack((east[keep], north[keep], z[usable][keep])))
    if not all(collected.values()):
        raise ValueError("The source crop needs both class-2 ground and class-17 bridge returns.")
    return {key: np.concatenate(values) for key, values in collected.items()}, source_tiles


def fit_local_alignment(ground, surface):
    w, s, e, n = FIT_EXTENT
    x = np.arange(w, e, 8)
    y = np.arange(s, n, 8)
    lattice = np.array([(px, py) for px in x for py in y], dtype=float)
    distance, index = cKDTree(ground[:, :2]).query(lattice, distance_upper_bound=1.8)
    residuals = [[], []]
    for i in np.flatnonzero(np.isfinite(distance)):
        px, py, pz = ground[index[i]]
        east_slope = (surface.height(px + 1, py) - surface.height(px - 1, py)) / 2
        north_slope = (surface.height(px, py + 1) - surface.height(px, py - 1)) / 2
        if math.hypot(east_slope, north_slope) <= 0.08:
            residuals[(i // len(y) + i % len(y)) % 2].append(float(surface.height(px, py) - pz))
    fit, holdout = map(np.asarray, residuals)
    if min(len(fit), len(holdout)) < 40:
        raise ValueError("Too few distributed class-2 witnesses for local alignment.")
    bias = float(np.median(fit))
    holdout_errors = holdout - bias
    median_error = float(np.median(holdout_errors))
    p95 = float(np.quantile(np.abs(holdout_errors), 0.95))
    if abs(median_error) > 0.10 or p95 > 0.22 or abs(bias) > 2:
        raise ValueError("The withheld ground witnesses failed the local visual alignment gate.")
    return bias, {
        "preview_dem_minus_raw_lidar_m": round(bias, 5),
        "fit_witnesses": len(fit), "holdout_witnesses": len(holdout),
        "holdout_median_signed_m": round(median_error, 4), "holdout_p95_abs_m": round(p95, 4),
        "method": "8 m checkerboard grid, ground class 2, slope <= 8%, nearest return <= 1.8 m",
        "scope": "station preview only; native LAZ Z, DEM tiles and regional registration gate remain unchanged",
    }


def station_ways(raw, nodes):
    wanted = {MAIN_STREET_OSM, *(way for route in CORRIDORS for way in route.ways)}
    ways = {}
    ground_roads = []
    for element in raw.findall("way"):
        ident = int(element.attrib["id"])
        properties = tags(element)
        highway = properties.get("highway")
        ground = (highway and highway not in {"footway", "steps", "path", "cycleway", "pedestrian", "bridleway"}
                  and properties.get("bridge", "no") == "no" and properties.get("tunnel", "no") == "no"
                  and properties.get("layer", "0") == "0")
        if not (ident in wanted or ground):
            continue
        ids = [int(nd.attrib["ref"]) for nd in element.findall("nd")]
        if len(ids) < 2 or any(ident not in nodes for ident in ids):
            if ident in wanted:
                raise ValueError(f"Incomplete locked OSM way {ident}.")
            continue
        coordinates = [nodes[ident]["local_en_m"] for ident in ids]
        if ident in wanted:
            ways[ident] = (ids, coordinates, int(element.attrib["version"]), properties)
        if ground:
            ground_roads.append(LineString(coordinates))
    if set(ways) != wanted:
        raise ValueError("One or more named station approach ways are missing from the locked capture.")
    return ways, ground_roads


def corridor_alignment(route, ways):
    coordinates, previous = [], None
    for ident in route.ways:
        ids, positions, _, properties = ways[ident]
        if previous is not None and previous != ids[0]:
            raise ValueError(f"Noncontiguous OSM geometry for {route.name}.")
        if (properties.get("bridge") != "yes" or int(properties.get("layer", "0")) != route.layer
                or (route.kind == "rail" and properties.get("railway") != "rail")
                or (route.kind != "rail" and properties.get("highway") not in {"motorway", "motorway_link"})):
            raise ValueError(f"Unexpected OSM class or layer for {route.name}.")
        coordinates.extend(positions[1:] if coordinates else positions)
        previous = ids[-1]
    line = LineString(coordinates).intersection(box(*route.bounds))
    if line.geom_type != "LineString" or line.length < 40:
        raise ValueError(f"Expected a continuous clipped approach for {route.name}.")
    return line


def point_stations(line):
    return np.linspace(0, line.length, math.ceil(line.length / STEP_M) + 1)


def match_returns(line, route, points, index):
    distances = point_stations(line)
    locations = np.array([line.interpolate(s).coords[0] for s in distances])
    candidates = index.query_ball_point(locations, RADIUS_M)
    observed = np.full(len(locations), np.nan)
    counts = []
    ranges = []
    for i, neighborhood in enumerate(candidates):
        heights = points[neighborhood, 2]
        plausible = heights[(heights >= route.lidar_band[0]) & (heights <= route.lidar_band[1])]
        counts.append(len(plausible))
        if len(plausible) < 20:
            ranges.append(None)
            continue
        low, center, high = np.quantile(plausible, [0.1, 0.5, 0.9])
        spread = float(high - low)
        ranges.append(round(spread, 3))
        if spread <= 0.45:
            observed[i] = center
    return distances, locations, observed, counts, ranges


def interpolate_profile(distances, observed, route):
    valid = np.flatnonzero(np.isfinite(observed))
    if len(valid) < 5 or valid[0] != 0 or valid[-1] != len(distances) - 1:
        raise ValueError(f"{route.name} lacks observed end anchors; extrapolation is disabled.")
    gaps = [
        (int(left), int(right), float(distances[right] - distances[left]))
        for left, right in zip(valid[:-1], valid[1:], strict=True) if right - left > 1
    ]
    largest = max((span for _, _, span in gaps), default=0.0)
    if largest > route.max_gap:
        raise ValueError(f"{route.name} class-17 gap reaches {largest:.2f} m, above the preview cap.")
    estimates = np.interp(distances, distances[valid], observed[valid])
    grade = float(np.max(np.abs(np.diff(estimates) / np.diff(distances))))
    if grade > route.max_grade:
        raise ValueError(f"Unreliable deck grade {grade:.3f} on {route.name}; check for returns from another structure.")
    return estimates, gaps, grade


def extract_profiles(ways, points, bias, surface):
    index = cKDTree(points[:, :2])
    main = LineString(ways[MAIN_STREET_OSM][1])
    profiles = []
    for route in CORRIDORS:
        line = corridor_alignment(route, ways)
        distances, locations, observed, counts, ranges = match_returns(line, route, points, index)
        values, gaps, grade = interpolate_profile(distances, observed, route)
        adjusted = values + bias
        crossing = line.intersection(main)
        if crossing.geom_type != "Point":
            raise ValueError(f"Expected one East Main Street crossing for {route.name}.")
        at = line.project(crossing)
        lower = min(max(int(np.searchsorted(distances, at)) - 1, 0), len(distances) - 2)
        estimate = float(np.interp(at, distances, adjusted))
        ground = float(surface.height(crossing.x, crossing.y))
        profiles.append({
            "name": route.name, "kind": route.kind, "layer": route.layer, "illustrative_width_m": route.width,
            "osm_ways": [{"id": ident, "version": ways[ident][2]} for ident in route.ways],
            "raw_lidar_z_band_m": list(route.lidar_band),
            "length_m": round(line.length, 2), "max_absolute_grade": round(grade, 4),
            "interpolation_gaps": [
                {"from_chainage_m": round(float(distances[a]), 2), "to_chainage_m": round(float(distances[b]), 2),
                 "span_m": round(span, 2)} for a, b, span in gaps
            ],
            "east_main": {
                "local_en_m": [round(crossing.x, 4), round(crossing.y, 4)],
                "deck_z_m_in_preview": round(estimate, 3), "ground_z_m_in_preview": round(ground, 3),
                "deck_surface_minus_ground_m": round(estimate - ground, 3),
                "support": ("interpolation_across_unseen_span" if any(a <= lower and lower < b for a, b, _ in gaps)
                            else "bracketed_by_observed_returns"),
            },
            "samples": [
                {"chainage_m": round(float(station), 4), "local_en_m": [round(float(x), 5), round(float(y), 5)],
                 "raw_class17_median_m": round(float(raw), 4) if np.isfinite(raw) else None,
                 "preview_deck_z_m": round(float(z), 4), "returns_in_band": cnt, "p90_minus_p10_m": spread}
                for station, (x, y), raw, z, cnt, spread in zip(
                    distances, locations, observed, adjusted, counts, ranges, strict=True)
            ],
        })
    return profiles


def build(args):
    from station_deck_mesh import assemble

    protected = (args.source_dir.resolve(), args.proj_grid_dir.resolve(), args.terrain.resolve())
    if any(file.resolve().is_relative_to(folder) for file in (args.output, args.report) for folder in protected):
        raise ValueError("Write the deck preview separately from the locked input directories.")
    grid = load_json(ROOT / "pilot/grid.json")
    tiles = load_json(ROOT / "pilot/tile_manifest.json")
    controls = load_json(ROOT / "pilot/controls.json")
    projection_lock = load_json(ROOT / "data/projection_lock.json")
    source_path = ROOT / "terrain/first_pair_sources.json"
    sources = load_json(source_path)
    audit_osm_capture(args.osm_capture, controls)
    audit_projection_assets(args.proj_grid_dir, projection_lock)
    surface = load_surface(args.terrain, grid, tiles)
    origin = tiles["origin_grid_m_en"]
    raw_xy = sources["source_reference"]["laz"]["horizontal_epsg"]
    operation = next(item["pipeline"] for item in projection_lock["operations"] if item["source_crs"] == f"EPSG:{raw_xy}")
    trans = pyproj.Transformer.from_pipeline(operation)
    points, source_tiles = read_cloud(args.source_dir, sources, trans, origin)
    bias, alignment = fit_local_alignment(points[2], surface)
    raw = ElementTree.parse(args.osm_capture).getroot()
    ways, roads = station_ways(raw, node_rows(
        raw, pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"]), origin, grid))
    profiles = extract_profiles(ways, points[17], bias, surface)
    geom = assemble(args.output, profiles, roads, surface)
    project = {"schema_version": 1, "mode": MODE, "horizontal_crs": grid["horizontal_crs"],
               "capture_sha256": controls["capture"]["sha256"], "attribution": controls["attribution"],
               "lidar_source_lock_sha256": digest(source_path), "lidar_tiles_used": source_tiles,
               "terrain_report_sha256": digest(args.terrain / "terrain_first_pair.json"),
               "local_preview_alignment": alignment, "geometry": geom, "profiles": profiles}
    write_json(args.output / "station_decks.json", project)
    summary = {**project, "profiles": [
        {**{k: v for k, v in route.items() if k != "samples"}, "samples": len(route["samples"]),
         "observed_stations": sum(s["raw_class17_median_m"] is not None for s in route["samples"])}
        for route in profiles]}
    write_json(args.report, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm-capture", type=Path, default=ROOT / "inputs/osm_pilot.osm")
    parser.add_argument("--terrain", type=Path, default=ROOT / "outputs/terrain-first-pair-dem-preview")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "inputs/terrain-first-pair")
    parser.add_argument("--proj-grid-dir", type=Path, default=ROOT / "inputs/projection-grids")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/station-decks")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/station_decks.json")
    args = parser.parse_args()
    if laspy is None:
        print("BLOCKED: Install requirements-gis.txt for station deck extraction.", file=sys.stderr)
        return 3
    try:
        result = build(args)
    except FileNotFoundError as exc:
        print(f"BLOCKED: Missing station deck input {exc.filename}.", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: The local held-out class-2 alignment gate passed.")
    for row in result["profiles"]:
        print(f'PASS: {row["name"]} {row["observed_stations"]}/{row["samples"]} observed stations, '
              f'{row["east_main"]["deck_surface_minus_ground_m"]:.2f} m surface separation at East Main.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
