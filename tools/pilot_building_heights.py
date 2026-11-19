"""Estimate first-pair building heights above local ground using the locked Richmond LiDAR."""

import argparse
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import sys
from xml.etree import ElementTree

from atomic_output import write_json
from pilot_contract import ROOT, audit_osm_capture, audit_projection_assets, load_json, pyproj
from pilot_street_graph import node_rows, tags

try:
    import laspy
    import numpy as np
    from scipy.spatial import cKDTree
    import shapely
    from shapely.affinity import scale
    from shapely.geometry import MultiPolygon, Polygon, box, mapping
except ImportError:
    laspy = None


GROUND_OUTER_BUFFER_M = 8.0
GROUND_INNER_BUFFER_M = 0.5
MIN_HEIGHT_M = 1.0
MAX_HEIGHT_M = 180.0
NUMERIC = r"[0-9]+(?:\.[0-9]+)?"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def merge_rings(segments):
    remaining = [list(line) for line in segments]
    rings = []
    while remaining:
        ring = remaining.pop(0)
        while ring[0] != ring[-1]:
            matches = [index for index, line in enumerate(remaining)
                       if ring[-1] in (line[0], line[-1])]
            if len(matches) != 1:
                raise ValueError("multipolygon does not have a unique closed ring")
            next_line = remaining.pop(matches[0])
            ring.extend(next_line[1:] if next_line[0] == ring[-1] else reversed(next_line[:-1]))
        if len(set(ring)) < 3:
            raise ValueError("building ring contains fewer than three distinct nodes")
        rings.append(ring)
    return rings


def building_tag(properties):
    return properties.get("building", "").lower() not in {"", "0", "no", "false"}


def extract_footprints(root, nodes, pair_box):
    ways = {int(way.attrib["id"]): way for way in root.findall("way")}
    coordinates = {node_id: data["local_en_m"] for node_id, data in nodes.items()}
    output, rejected = [], []
    consumed = set()

    def add(kind, element, properties, geometry):
        source_id = f'osm/{kind}/{element.attrib["id"]}'
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
            rejected.append(source_id)
            return False
        output.append((source_id, int(element.attrib["version"]), properties, geometry))
        return True

    for relation in root.findall("relation"):
        properties = tags(relation)
        if not building_tag(properties) or properties.get("type") != "multipolygon":
            continue
        try:
            outer, inner, members = [], [], []
            for member in relation.findall("member"):
                role = member.attrib.get("role")
                if role in {"outer", "inner", ""} and member.attrib["type"] == "way":
                    way_id = int(member.attrib["ref"])
                    line = [int(node.attrib["ref"]) for node in ways[way_id].findall("nd")]
                    (inner if role == "inner" else outer).append(line)
                    members.append(way_id)
            shells = [Polygon([coordinates[i] for i in ring]) for ring in merge_rings(outer)]
            holes = [Polygon([coordinates[i] for i in ring]) for ring in merge_rings(inner)]
            if not shells:
                raise ValueError("multipolygon has no outer rings")
            assigned = [[] for _ in shells]
            for hole in holes:
                containing = [i for i, shell in enumerate(shells) if shell.covers(hole)]
                if not containing:
                    raise ValueError("building hole is outside all outer rings")
                owner = min(containing, key=lambda index: shells[index].area)
                assigned[owner].append(hole.exterior.coords)
            parts = [Polygon(shell.exterior.coords, interior) for shell, interior in zip(shells, assigned)]
            geometry = parts[0] if len(parts) == 1 else MultiPolygon(parts)
            if add("relation", relation, properties, geometry):
                consumed.update(members)
        except (KeyError, IndexError, ValueError, shapely.errors.GEOSException):
            rejected.append(f'osm/relation/{relation.attrib["id"]}')

    for way_id, way in ways.items():
        properties = tags(way)
        if way_id in consumed or not building_tag(properties):
            continue
        line = [int(item.attrib["ref"]) for item in way.findall("nd")]
        if len(line) < 4 or line[0] != line[-1] or any(node not in coordinates for node in line):
            rejected.append(f"osm/way/{way_id}")
            continue
        add("way", way, properties, Polygon([coordinates[node] for node in line]))

    footprints = sorted(output, key=lambda item: item[0])
    context_bounds = pair_box.buffer(GROUND_OUTER_BUFFER_M)
    placed = [row for row in footprints if pair_box.covers(row[3])]
    context = [row[3] for row in footprints if context_bounds.intersects(row[3])]
    return placed, context, sorted(rejected)


def cloud_samples(source_dir, source_lock, projection, origin, bounds):
    w, s, e, n = bounds
    dx, dy = origin
    raw = projection.transform_bounds(w + dx, s + dy, e + dx, n + dy, densify_pts=21, direction="INVERSE")
    points = {2: [], 6: []}
    reference = source_lock["source_reference"]["laz"]
    expected = [reference["horizontal_epsg"], reference["vertical_epsg"]]
    assets = [asset for asset in source_lock["assets"] if asset["kind"] == "laz"]
    if not assets:
        raise ValueError("The first-pair source lock contains no LiDAR files.")
    for asset in assets:
        path = source_dir / asset["file"]
        if path.stat().st_size != asset["bytes"] or digest(path) != asset["sha256"]:
            raise ValueError(f"LiDAR source bytes differ from the lock: {path.name}")
        with laspy.open(path) as reader:
            crs = reader.header.parse_crs()
            if not crs or [part.to_epsg() for part in crs.sub_crs_list] != expected:
                raise ValueError(f"Unexpected LiDAR CRS in {path.name}.")
            for chunk in reader.chunk_iterator(300_000):
                cls = np.asarray(chunk.classification)
                lx, ly = np.asarray(chunk.x), np.asarray(chunk.y)
                valid = (~np.asarray(chunk.withheld, dtype=bool) & ((cls == 2) | (cls == 6))
                         & (lx >= raw[0] - 1) & (lx <= raw[2] + 1) & (ly >= raw[1] - 1) & (ly <= raw[3] + 1))
                if not valid.any():
                    continue
                x, y = projection.transform(lx[valid], ly[valid], errcheck=True)
                x, y = x - dx, y - dy
                z = np.asarray(chunk.z)[valid]
                classification = cls[valid]
                inside = (x >= w) & (x <= e) & (y >= s) & (y <= n)
                for kind in points:
                    choose = inside & (classification == kind)
                    if choose.any():
                        points[kind].append(np.column_stack((x[choose], y[choose], z[choose])))
    if not all(points.values()):
        raise ValueError("No usable classified ground or building points in the first pair.")
    return {kind: np.concatenate(chunks) for kind, chunks in points.items()}, len(assets)


def around(positions, index, geometry):
    w, s, e, n = geometry.bounds
    indices = index.query_ball_point(((w + e) / 2, (s + n) / 2), math.hypot(e - w, n - s) / 2)
    return positions[indices]


def split_roof_delta(roof):
    parity = np.floor(roof[:, :2]).astype(int).sum(axis=1) % 2
    splits = [roof[parity == branch, 2] for branch in (0, 1)]
    if min(map(len, splits)) < 10:
        return None
    return round(abs(float(np.quantile(splits[0], 0.95) - np.quantile(splits[1], 0.95))), 3)


def measure(footprint, roof, ground):
    roof_cells = len(np.unique(np.floor(roof[:, :2]).astype(int), axis=0))
    density = min(1.0, roof_cells / footprint.area)
    top = float(np.quantile(roof[:, 2], 0.95)) if len(roof) else None
    base = float(np.median(ground[:, 2])) if len(ground) else None
    relief = float(np.ptp(np.quantile(ground[:, 2], [0.10, 0.90]))) if len(ground) else None
    height = top - base if top is not None and base is not None else None
    issues = []
    if len(roof) < 10 or density < 0.30:
        issues.append("sparse_class_6")
    if len(ground) < 20:
        issues.append("sparse_class_2")
    if relief is not None and relief > 2.5:
        issues.append("varied_nearby_ground")
    if footprint.area < 4:
        issues.append("small_footprint")
    if height is not None and not MIN_HEIGHT_M <= height <= MAX_HEIGHT_M:
        issues.append("implausible_height")
    return {
        "relative_lidar_candidate_m": round(height, 3) if height is not None else None,
        "roof_point_count": len(roof), "occupied_1m_roof_cells": roof_cells, "roof_coverage": round(density, 3),
        "ground_point_count": len(ground), "ground_p90_minus_p10_m": round(relief, 3) if relief is not None else None,
        "roof_split_difference_m": split_roof_delta(roof), "quality_flags": issues,
    }


def tag_height(properties):
    raw = properties.get("height", "").strip()
    metric = re.fullmatch(fr"({NUMERIC})\s*(m|ft|feet)?", raw, flags=re.IGNORECASE)
    imperial = re.fullmatch(fr"({NUMERIC})'\s*(?:({NUMERIC})\x22)?", raw)
    if metric:
        units = (metric[2] or "m").lower()
        value = float(metric[1]) * (1.0 if units == "m" else 0.3048)
    elif imperial:
        value = float(imperial[1]) * 0.3048 + float(imperial[2] or 0) * 0.0254
    else:
        value = 0.0
    if MIN_HEIGHT_M <= value <= MAX_HEIGHT_M:
        return round(value, 3), "osm_height"

    levels = properties.get("building:levels", "").strip()
    if re.fullmatch(NUMERIC, levels) and 1 <= float(levels) <= 50:
        return round(float(levels) * 3.0 + 0.8, 3), "osm_levels_estimate"
    return None, "unresolved"


def analyze(footprints, context, points):
    occupied = shapely.union_all(context)
    shapely.prepare(occupied)
    roof_points, ground_points = points[6], points[2]
    roof_index = cKDTree(roof_points[:, :2])
    ground_index = cKDTree(ground_points[:, :2])
    rows = []
    for feature_id, version, properties, footprint in footprints:
        search = footprint.buffer(GROUND_OUTER_BUFFER_M).difference(footprint.buffer(GROUND_INNER_BUFFER_M))
        roof = around(roof_points, roof_index, footprint)
        roof = roof[shapely.contains_xy(footprint, roof[:, 0], roof[:, 1])]
        ground = around(ground_points, ground_index, search)
        ground = ground[shapely.contains_xy(search, ground[:, 0], ground[:, 1])
                        & ~shapely.contains_xy(occupied, ground[:, 0], ground[:, 1])]
        data = measure(footprint, roof, ground)
        if not data["quality_flags"] and data["relative_lidar_candidate_m"] is not None:
            value, method = data["relative_lidar_candidate_m"], "lidar_class_6_minus_class_2"
        else:
            value, method = tag_height(properties)
        kind = properties["building"]
        xy = shapely.orient_polygons(scale(footprint, xfact=100, yfact=-100, origin=(0, 0)))
        owner = footprint.representative_point()
        rows.append({
            "id": feature_id, "osm_version": version, "building_type": kind,
            "name": properties.get("name"), "relative_height_m": value, "height_source": method,
            "area_m2": round(footprint.area, 3), "position_local_en_m": [round(owner.x, 3), round(owner.y, 3)],
            "footprint_unreal_xy_cm": mapping(xy), **data,
        })
    return rows


def summarize(features):
    sources = Counter(row["height_source"] for row in features)
    candidates = sorted(
        (row for row in features if row["roof_split_difference_m"] is not None),
        key=lambda row: (row["position_local_en_m"][0], row["position_local_en_m"][1], row["id"]),
    )
    uneven = [row for row in candidates if "varied_nearby_ground" in row["quality_flags"]]
    selected = {uneven[index]["id"]: uneven[index]
                for index in np.linspace(0, len(uneven) - 1, min(5, len(uneven)), dtype=int)}
    others = [row for row in candidates if row["id"] not in selected]
    for index in np.linspace(0, len(others) - 1, min(30 - len(selected), len(others)), dtype=int):
        selected[others[index]["id"]] = others[index]
    residuals = [row["roof_split_difference_m"] for row in selected.values()]
    return {"footprints": len(features), "height_sources": dict(sources),
            "quality_flags": dict(Counter(flag for row in features for flag in row["quality_flags"])),
            "internal_roof_repeatability": {
                "samples": len(residuals),
                "varied_ground_samples": sum("varied_nearby_ground" in row["quality_flags"] for row in selected.values()),
                "median_difference_m": round(float(np.median(residuals)), 3) if residuals else None,
                "p95_difference_m": round(float(np.quantile(residuals, 0.95)), 3) if residuals else None,
                "sample_ids": list(selected),
            }}


def build(args):
    output, report = args.output.resolve(), args.report.resolve()
    if output == report or any(path == args.osm_capture.resolve() or path.is_relative_to(args.source_dir.resolve())
                               or path.is_relative_to(args.proj_grid_dir.resolve()) for path in (output, report)):
        raise ValueError("The inputs and outputs must use distinct paths.")

    controls = load_json(ROOT / "pilot/controls.json")
    grid = load_json(ROOT / "pilot/grid.json")
    manifest = load_json(ROOT / "pilot/tile_manifest.json")
    audit_osm_capture(args.osm_capture, controls)
    projection_lock = load_json(ROOT / "data/projection_lock.json")
    audit_projection_assets(args.proj_grid_dir, projection_lock)
    source_path = ROOT / "terrain/first_pair_sources.json"
    source_lock = load_json(source_path)
    osm_projection = pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"])
    origin = osm_projection.transform(*grid["origin_wgs84_lon_lat"], errcheck=True)
    horizontal_epsg = source_lock["source_reference"]["laz"]["horizontal_epsg"]
    operation = next(op for op in projection_lock["operations"] if op["source_crs"] == f"EPSG:{horizontal_epsg}")
    cloud_projection = pyproj.Transformer.from_pipeline(operation["pipeline"])
    pair_ids = {tuple(index) for index in grid["first_adjacent_tiles_en"]}
    pair_tiles = [box(*tile["local_bounds_m"]) for tile in manifest["tiles"] if tuple(tile["index_en"]) in pair_ids]
    if len(pair_tiles) != 2:
        raise ValueError("Expected the two locked terrain tiles in the current pilot manifest.")
    pair = shapely.union_all(pair_tiles)
    raw = ElementTree.parse(args.osm_capture).getroot()
    footprints, context, rejected = extract_footprints(raw, node_rows(raw, osm_projection, origin, grid), pair)
    if not footprints:
        raise ValueError("No complete OSM footprints in the first terrain pair.")
    points, file_count = cloud_samples(args.source_dir, source_lock, cloud_projection, origin,
                                      pair.buffer(GROUND_OUTER_BUFFER_M + 1).bounds)
    rows = analyze(footprints, context, points)
    summary = summarize(rows)
    if not summary["height_sources"].get("lidar_class_6_minus_class_2"):
        raise ValueError("No footprints met the relative LiDAR height checks.")
    artefact = {"schema_version": 1, "horizontal_crs": grid["horizontal_crs"], "osm_source": controls["capture"],
                "osm_attribution": controls["attribution"], "license_url": controls["license_url"],
                "lidar_source_lock_sha256": digest(source_path), "relative_heights_only": True, "footprints": rows}
    write_json(args.output, artefact)
    report = {**summary, "export_sha256": digest(args.output), "lidar_files_verified": file_count,
              "input_point_counts": {kind: len(samples) for kind, samples in points.items()},
              "expected_lidar_source_crs": [horizontal_epsg, source_lock["source_reference"]["laz"]["vertical_epsg"]],
              "capture_sha256": controls["capture"]["sha256"], "lidar_source_lock_sha256": digest(source_path),
              "invalid_footprint_ids_in_capture": rejected}
    write_json(args.report, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm-capture", type=Path, default=ROOT / "inputs/osm_pilot.osm")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "inputs/terrain-first-pair")
    parser.add_argument("--proj-grid-dir", type=Path, default=ROOT / "inputs/projection-grids")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/pilot_building_heights.json")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/pilot_building_heights.json")
    args = parser.parse_args()
    if laspy is None or pyproj is None:
        print("BLOCKED: Install requirements-gis.txt before running the height export.", file=sys.stderr)
        return 3
    try:
        report = build(args)
    except FileNotFoundError as error:
        print(f"BLOCKED: Missing locked input {error.filename}", file=sys.stderr)
        return 3
    except (ValueError, OSError, KeyError, StopIteration, pyproj.exceptions.ProjError,
            ElementTree.ParseError, shapely.errors.GEOSException) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f'PASS: {report["footprints"]} complete footprints and {report["height_sources"]}.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
