"""Dress the mapped East Main route through 21st Street for the Godot drive."""

import math
from collections import Counter
from xml.etree import ElementTree

from shapely.affinity import affine_transform
from shapely.geometry import LineString, box

from atomic_output import write_json, write_text
from build_pilot_mesh_preview import MATERIALS, Obj, Surface, landscape, load_surface, massing
from pilot_building_heights import analyze, cloud_samples, extract_footprints, node_rows
from pilot_contract import ROOT, audit_osm_capture, audit_projection_assets, load_json
from station_approach import Drape, offset_band
from terrain_first_pair import SURVEY_FOOT_METRES, bilinear, height_codes, mosaic_dem, np, pyproj, verify_asset


OUTPUT = ROOT / "outputs/east-main-corridor"
START, END = 42.9, 545.0
INTERSECTIONS = {"17th": 49615897, "18th": 49615895, "19th": 49615892, "20th": 49615890, "21st": 49614001}
EXTRA_BOUNDS = (-402, -76, -232, 0)
PALETTE = {"corridor_road": (0.19, 0.18, 0.17), "corridor_walk": (0.46, 0.37, 0.30),
           "corridor_yellow": (0.76, 0.54, 0.18), "corridor_white": (0.76, 0.73, 0.66)}


def supplement_terrain(old, grid, origin, lock, project):
    west, south, east, north = EXTRA_BOUNDS
    e0, n0 = origin
    assets = []
    for entry in lock["assets"]:
        if entry["kind"] != "dem":
            continue
        path = ROOT / "inputs/terrain-first-pair" / entry["file"]
        if not verify_asset(path, entry):
            raise ValueError(f"Unexpected DEM source {path.name}")
        assets.append(path)
    native_bounds = project.transform_bounds(e0 + west - 3, n0 + south - 3, e0 + east + 3, n0 + north + 3,
                                             direction="INVERSE", densify_pts=21)
    raster, transform = mosaic_dem(assets, lock["source_reference"]["dem"], native_bounds)
    step = old.step
    x, y = np.meshgrid(e0 + np.arange(west, east + step, step), n0 + np.arange(north, south - step, -step))
    native_x, native_y = project.transform(x, y, direction="INVERSE", errcheck=True)
    codes = height_codes(bilinear(raster, transform, native_x, native_y) * SURVEY_FOOT_METRES, grid)
    heights = (codes.astype(float) - grid["height_code_zero"]) / grid["height_codes_per_m"]
    seam = np.array([old.height(e, 0) for e in np.arange(west, east + step, step)])
    if np.max(np.abs(heights[0] - seam)) > 0.008:
        raise ValueError("The corridor extension must meet the existing DEM seam.")
    heights[0] = seam
    return Surface(heights, EXTRA_BOUNDS, step)


def main():
    grid, manifest = (load_json(ROOT / f"pilot/{name}.json") for name in ("grid", "tile_manifest"))
    origin = manifest["origin_grid_m_en"]
    approach = load_json(ROOT / "reports/station_approach.json")
    graph = load_json(ROOT / "inputs/pilot_street_graph.json")
    if graph["source"]["sha256"] != load_json(ROOT / "pilot/controls.json")["capture"]["sha256"]:
        raise ValueError("The road graph and building capture differ.")
    nodes = {item["id"]: item["local_en_m"] for item in graph["nodes"]}
    origin_en = nodes[12101815230]
    basis = approach["station_frame"]
    tx, tn = basis[0][0], basis[1][0]
    norm = math.hypot(tx, tn)
    tx, tn = tx / norm, tn / norm
    east, north = origin_en

    def route(point):
        e, n = point[0] - east, point[1] - north
        return tx * e + tn * n, tn * e - tx * n

    def world(geometry):
        return affine_transform(geometry, [tx, tn, tn, -tx, east, north])

    node_ids = {edge[k] for edge in graph["edges"] if edge["name"] == "East Main Street"
                and not (edge["bridge"] or edge["tunnel"] or edge["layer"]) for k in ("a", "b")}
    center = sorted((s, d) for i in node_ids for s, d in [route(nodes[i])] if 0 <= s <= END + 60 and abs(d) < 10)
    along, tangent = zip(*center)

    def lateral(s):
        return float(np.interp(s, along, tangent))

    intersections = {name: route(nodes[node]) for name, node in INTERSECTIONS.items()}
    reference = load_json(ROOT / "data/projection_lock.json")
    grid_dir = ROOT / "inputs/projection-grids"
    audit_projection_assets(grid_dir, reference)
    pyproj.datadir.append_data_dir(grid_dir)
    pipelines = {item["source_crs"]: item["pipeline"] for item in reference["operations"]}
    lock = load_json(ROOT / "terrain/first_pair_sources.json")
    first = load_surface(ROOT / "inputs/terrain-preview", grid, manifest)
    extra = supplement_terrain(first, grid, origin, lock, pyproj.Transformer.from_pipeline(pipelines["EPSG:2925"]))

    obj = Obj("East_Main_Corridor.mtl")
    landscape(obj, extra)
    obj.lines[2] = "o Corridor_Terrain"
    drapes = [Drape(obj, surface) for surface in (first, extra)]

    def drape(path, finish, offset, sealed=False):
        polygon = world(path)
        for builder in drapes:
            builder.add(polygon.intersection(builder.surface.footprint), finish, lambda *_: offset, sealed=sealed)

    xs = sorted({START, END, 58, *(s for s, _ in center if START < s < END)})
    middles = np.array([lateral(s) for s in xs])
    widths = np.interp(xs, [START, 58, END], [4, 7.35, 7.35])
    road = offset_band(xs, middles - widths, middles + widths)
    corners = [box(s - 4.8, d - 21, s + 4.8, d + 21) for s, d in intersections.values()]
    obj.group("Corridor_Road")
    drape(road.union(corners[0]).union(corners[1]).union(corners[2]).union(corners[3]).union(corners[4]),
          "corridor_road", 0.125)
    obj.group("Corridor_Sidewalks")
    for side in (-1, 1):
        inner = middles + side * widths
        outer = inner + side * 2.35
        sidewalk = offset_band(xs, np.minimum(inner, outer), np.maximum(inner, outer))
        for corner in corners:
            sidewalk = sidewalk.difference(corner.buffer(1.2, cap_style="square"))
        drape(sidewalk.intersection(box(START + 3, -30, END, 30)), "corridor_walk", 0.27, sealed=True)

    obj.group("Corridor_Markings")
    for delta in (-0.14, 0.14):
        stripe = LineString([(s, d + delta) for s, d in zip(xs, middles)]).buffer(0.053, cap_style="flat")
        for corner in corners:
            stripe = stripe.difference(corner.buffer(4.8))
        drape(stripe, "corridor_yellow", 0.141)
    for s in range(63, 542, 8):
        if any(abs(s - c) < 13 for c, _ in intersections.values()):
            continue
        d = lateral(s)
        for offset in (-4.5, 4.55):
            drape(box(s, d + offset - 0.056, s + 3.1, d + offset + 0.056), "corridor_white", 0.141)
    for s, d in intersections.values():
        for x in (s - 7.3, s + 6.2):
            for i in range(-6, 7, 2):
                drape(box(x, d + i - 0.37, x + 2.2, d + i + 0.37), "corridor_white", 0.143)

    # Extend the existing footprint and relative height pipeline only where the first pair omitted complete buildings.
    old_buildings = load_json(ROOT / "inputs/pilot_building_heights.json")["footprints"]
    capture = ROOT / "inputs/osm_pilot.osm"
    audit_osm_capture(capture, load_json(ROOT / "pilot/controls.json"))
    osm = ElementTree.parse(capture).getroot()
    projection = pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"])
    selected, context, _ = extract_footprints(osm, node_rows(osm, projection, origin, grid), box(-413, -76, -230, 97))
    previous = {row["id"] for row in old_buildings if row["relative_height_m"] is not None}
    desired = world(box(399, -49, END + 54, 49))
    added = [item for item in selected if item[0] not in previous and desired.intersects(item[3])]
    if not added:
        raise ValueError("No additional building footprints found for the 21st Street approach.")
    points, _ = cloud_samples(ROOT / "inputs/terrain-first-pair", lock,
                              pyproj.Transformer.from_pipeline(pipelines["EPSG:3748"]), origin,
                              desired.buffer(20).bounds)
    rows = analyze(added, context, points)
    for surface, criterion in ((extra, lambda n: n < 0), (first, lambda n: n >= 0)):
        massing(obj, surface, [row for row in rows if criterion(row["position_local_en_m"][1])])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_text(OUTPUT / "East_Main_Corridor.obj", "\n".join(obj.lines) + "\n")
    write_text(OUTPUT / "East_Main_Corridor.mtl", "\n".join(f"newmtl {name}\nKd {r} {g} {b}\n"
               for name, (r, g, b) in (MATERIALS | PALETTE).items()))
    report = {"origin_en": list(origin_en), "east_axis_en": [tx, tn], "centerline": [list(p) for p in center],
              "intersections": intersections, "extent": [START, END], "start_at": END - 15,
              "extra_dem_local_bounds": EXTRA_BOUNDS, "road_source_sha256": graph["source"]["sha256"],
              "drape_max_error_m": round(max(d.max_interpolation_error for d in drapes), 6),
              "added_building_heights": dict(Counter(row["height_source"] for row in rows)),
              "overlay_terrain_triangles": sum(d.triangles for d in drapes)}
    write_json(OUTPUT / "corridor.json", report)
    write_json(ROOT / "reports/east_main_corridor.json", report)
    print(f"PASS: Draped 17th–21st Street and joined the 2025 DEM at northing 0. {len(rows)} supplemental footprint heights checked.")


if __name__ == "__main__":
    main()
