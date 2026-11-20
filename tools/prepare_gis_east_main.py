"""Build the authored East Main street surfaces on a saved Godot GIS snapshot."""

import argparse
import math
from pathlib import Path
import sys

import numpy as np
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box

from atomic_output import write_json
from build_pilot_mesh_preview import Surface
from fetch_rva_gis import ORIGIN_EN, load_json, sha256
from station_approach import Drape, StationApproach, offset_band


ROOT = Path(__file__).resolve().parents[1]
PALETTE = {
    "approach_asphalt": "#3c3d41", "approach_brick": "#8a4c41",
    "approach_white": "#dedacf", "approach_yellow": "#d5a548",
    "approach_walk": "#a29b92", "approach_curb": "#bcb6ac",
    "corridor_road": "#3c3d41", "corridor_walk": "#a29b92",
    "corridor_curb": "#bcb6ac", "corridor_yellow": "#d5a548", "corridor_white": "#dedacf",
}


class StreetParts:
    """Collect the exact vertex and face stream emitted by the shared draper."""

    def __init__(self):
        self.parts = {}
        self.points = []
        self.active = ""
        self.finish = ""

    def group(self, name):
        self.active = name

    def material(self, name):
        self.finish = name

    def vertex(self, point):
        east, north, up = point
        self.points.append([round(float(value), 5) for value in (east, up, -north)])
        return len(self.points) - 1

    def face(self, vertices):
        part = self.parts.setdefault(self.active, {})
        part.setdefault(self.finish, []).append(vertices)


def read_surface(folder, source):
    grid = source["heightmap"]
    if (source.get("schema") != "rva-gis/1" or source["horizontal_epsg"] != 26918
            or grid["surface_model"] != "linear_triangles_nw_se" or grid["sample_position"] != "pixel_center"):
        raise ValueError("Expected the RVA GIS triangle heightfield in EPSG:26918.")
    raw = folder / grid["raw_little_endian_uint16"]
    if sha256(raw) != source["files_sha256"][raw.name]:
        raise ValueError("The R16 terrain differs from the GIS snapshot.")
    columns, rows = grid["size_px"]
    dx, dy = grid["pixel_size_en_m"]
    e, n = source["origin_grid_m_en"]
    west, south, east, north = grid["bounds_en_m"]
    bounds = west - e + dx / 2, south - n + dy / 2, east - e - dx / 2, north - n - dy / 2
    heights = np.fromfile(raw, dtype="<u2").reshape(rows, columns).astype(float)
    heights = heights * grid["z_scale_per_code_m"] + grid["z_offset_m"] - source["origin_elevation_m"]
    return Surface(heights, bounds, dx, dy)


def road_inputs(data_dir, source):
    roads = data_dir / "rva_roads.geojson"
    if sha256(roads) != source["files_sha256"][roads.name]:
        raise ValueError("The OSM roads differ from the GIS snapshot.")
    nodes, edges, main = [], [], []
    for feature in load_json(roads)["features"]:
        props = feature["properties"]
        tags = props["tags"]
        if (tags.get("bridge", "no") not in ("no", "0")
                or tags.get("tunnel", "no") not in ("no", "0")
                or tags.get("layer", "0") != "0"):
            continue
        coords = [(e, -s) for e, s in props["centerline_local_xz_m"]]
        if len(coords) < 2:
            continue
        base = len(nodes)
        nodes.extend({"id": base + i, "local_en_m": point} for i, point in enumerate(coords))
        edges.extend({"a": base + i, "b": base + i + 1, "way": props["osm_id"],
                      "bridge": False, "tunnel": False, "layer": 0} for i in range(len(coords) - 1))
        if tags.get("name") == "East Main Street":
            main.append(LineString(coords))
    return {"nodes": nodes, "edges": edges}, shapely.union_all(main)


def draft_corridor(sink, surface, corridor, approach, source_shift):
    east, north = np.asarray(corridor["origin_en"]) + source_shift
    tx, tn = corridor["east_axis_en"]
    ref = [tx, tn, tn, -tx, east, north]
    west, end = corridor["extent"]
    along, offsets = np.asarray(corridor["centerline"]).T

    def world(geometry):
        return affine_transform(geometry, ref)

    def lateral(s):
        return float(np.interp(s, along, offsets))

    def road_height(e, n):
        station = tx * (e - east) + tn * (n - north)
        return float(np.interp(station, [west, west + 8], [0.12, 0.125]))

    xs = sorted({west, 58, end, *(s for s in along if west < s < end)})
    middle = np.interp(xs, along, offsets)
    widths = np.interp(xs, [west, 58, end], [4, 7.35, 7.35])
    junctions = list(corridor["intersections"].values())
    corners = shapely.union_all([box(s - 4.8, d - 21, s + 4.8, d + 21) for s, d in junctions])
    street = offset_band(xs, middle - widths, middle + widths).union(corners)
    sidewalk, curb = [], []
    for side in (-1, 1):
        inner = middle + side * widths
        detail = inner + side * 0.18
        outer = inner + side * 2.35
        sidewalk.append(offset_band(xs, np.minimum(detail, outer), np.maximum(detail, outer)))
        curb.append(offset_band(xs, np.minimum(inner, detail), np.maximum(inner, detail)))
    corner_clear = corners.buffer(1.2, cap_style="square")
    sidewalk = shapely.union_all(sidewalk).difference(corner_clear)
    curb = shapely.union_all(curb).difference(corner_clear)
    yellow = shapely.union_all([LineString([(s, d + delta) for s, d in zip(xs, middle)]).buffer(
        0.053, cap_style="flat").difference(corners.buffer(4.8)) for delta in (-0.14, 0.14)])
    white = []
    for s in range(63, 542, 8):
        if all(abs(s - x) >= 13 for x, _ in junctions):
            for offset in (-4.5, 4.55):
                d = lateral(s) + offset
                white.append(box(s, d - 0.056, s + 3.1, d + 0.056))
    for s, d in junctions:
        for x in (s - 7.3, s + 6.2):
            white.extend(box(x, d + i - 0.37, x + 2.2, d + i + 0.37) for i in range(-6, 7, 2))
    white_paint = shapely.union_all(white).intersection(street)
    yellow_paint = yellow.intersection(street)
    surface_bound = surface.footprint.buffer(0.001)
    drape = Drape(sink, surface)

    def paint_height(e, n):
        return road_height(e, n) + 0.016

    for index, left in enumerate(np.arange(west, end, 104)):
        right = min(left + 104, end)
        region = box(left, -32, right, 32)
        sink.group(f"corridor_{index}")
        for name, polygon, height, sealed in (
            ("corridor_road", street, road_height, False),
            ("corridor_walk", sidewalk, lambda *_: 0.27, True),
            ("corridor_curb", curb, lambda *_: 0.27, True),
            ("corridor_white", white_paint, paint_height, False),
            ("corridor_yellow", yellow_paint, paint_height, False),
        ):
            footprint = world(polygon.intersection(region)).difference(approach.replacement)
            if not surface_bound.covers(footprint):
                raise ValueError("The GIS snapshot must cover the 21st Street corridor.")
            drape.add(footprint, name, height, sealed=sealed)
    return [float(east), float(north)]


def build(data_dir, chunks_path, output):
    snapshot = data_dir / "rva_gis_manifest.json"
    source = load_json(snapshot)
    snapshot_hash = sha256(snapshot)
    surface = read_surface(data_dir, source)
    graph, main = road_inputs(data_dir, source)
    corridor = load_json(ROOT / "reports/east_main_corridor.json")
    frame = np.asarray(load_json(ROOT / "reports/station_approach.json")["station_frame"], dtype=float)
    shift = np.asarray(ORIGIN_EN) - np.asarray(source["origin_grid_m_en"])
    frame[:2, 3] += shift
    frame[2, 3] -= source["origin_elevation_m"]
    station_y = None
    if chunks_path.is_file():
        chunks = load_json(chunks_path)
        if chunks["source_manifest_sha256"] != snapshot_hash:
            raise ValueError("The station chunks must use this GIS snapshot.")
        for station in chunks.get("landmarks", []):
            if station["id"] == "main_street_station":
                station_y = station["origin_godot_m"][1]
                frame[2, 3] = station_y
    approach = StationApproach(graph, frame, surface)
    sink = StreetParts()
    evidence = approach.add(sink)
    origin = draft_corridor(sink, surface, corridor, approach, shift)
    tx, tn = corridor["east_axis_en"]

    def centerline_point(s, d):
        return origin[0] + tx * s + tn * d, origin[1] + tn * s - tx * d

    center = LineString([centerline_point(s, d) for s, d in corridor["centerline"] if s <= corridor["start_at"]])
    drift = max(center.interpolate(d).distance(main) for d in range(0, math.floor(center.length), 4))
    if drift > 0.9:
        raise ValueError(f"Archived gameplay route differs from the GIS road by {drift:.2f} m.")

    def game_camera(point):
        x, n, y, _ = frame @ [*point, 1]
        return [float(x - origin[0]), float(y), float(origin[1] - n)]

    views = [
        {"name": name, "eye": game_camera(eye), "target": game_camera(target), "fov": fov}
        for name, eye, target, fov in (
            ("Southwest facade", (7, -23.1, -0.86), (14, 0, 11.8), 68.0),
            ("Southeast platform", (80.5, 10, -0.77), (11, 45, 10.1), 64.0),
        )
    ]
    doc = {
        "schema": "rva-gis-east-main/1", "snapshot_sha256": snapshot_hash,
        "station_y_m": station_y, "palette": PALETTE, "vertices": sink.points, "parts": sink.parts,
        "route": {"origin_en": origin, "eastbound_xz": [tx, -tn], "east_main_centerline": corridor["centerline"],
                  "start_at": corridor["start_at"], "end_at": corridor["extent"][1] - 1,
                  "attribution": source["attributions"]["vectors"], "station_views": views},
        "checks": {"centerline_max_drift_m": round(drift, 4), "station_witnesses": evidence["witnesses"],
                   "intersections": corridor["intersections"]},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, doc)
    print(f"PASS: Built East Main roadway, curb, sidewalk and marking geometry in {len(sink.parts)} groups. "
          f"Route differs from the saved OSM centerline by at most {drift:.3f} m.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("outputs/rva_gis"))
    parser.add_argument("--chunks-manifest", type=Path,
                        default=Path("godot/station_trial/assets/rva_gis/meshes/rva_chunks.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/rva_gis_east_main/east_main.json"))
    args = parser.parse_args()
    try:
        build(args.data_dir, args.chunks_manifest, args.output)
    except (OSError, ValueError, shapely.errors.GEOSException) as error:
        sys.exit(f"East Main street build failed. {error}")


if __name__ == "__main__":
    main()
