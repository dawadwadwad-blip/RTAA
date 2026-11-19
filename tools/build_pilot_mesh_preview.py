"""Assemble the western Richmond pair into a local-meter mesh preview for Blender."""

import argparse
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import sys

from atomic_output import write_json, write_text
from pilot_contract import ROOT, load_json

try:
    import numpy as np
    import shapely
    from shapely.affinity import scale
    from shapely.geometry import LineString, box, shape
except ImportError:
    shapely = None


STRIDE = 2
ROAD_WIDTH_M = {"motorway": 10.5, "trunk": 9.0, "primary": 8.0, "secondary": 7.0, "tertiary": 6.5,
                "service": 3.6, "track": 3.0}
MATERIALS = {
    "terrain": (0.34, 0.41, 0.32),
    "asphalt": (0.20, 0.23, 0.26),
    "path": (0.60, 0.58, 0.51),
    "brick": (0.59, 0.25, 0.18),
    "slate": (0.29, 0.31, 0.36),
}


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@dataclass(frozen=True)
class Surface:
    elevations: object
    bounds: tuple
    step: float

    @property
    def footprint(self):
        return box(*self.bounds)

    def height(self, east, north):
        west, _, _, north_edge = self.bounds
        row = min(max(0.0, (north_edge - north) / self.step), self.elevations.shape[0] - 1)
        col = min(max(0.0, (east - west) / self.step), self.elevations.shape[1] - 1)
        r = min(int(row), self.elevations.shape[0] - 2)
        c = min(int(col), self.elevations.shape[1] - 2)
        v, u = row - r, col - c
        nw, ne = self.elevations[r, c:c + 2]
        sw, se = self.elevations[r + 1, c:c + 2]
        if v >= u:
            return nw + (sw - nw) * v + (se - sw) * u
        return nw + (ne - nw) * u + (se - ne) * v


def load_surface(directory, grid, manifest):
    report = load_json(directory / "terrain_first_pair.json")
    span = grid["tile_span_m"]
    expected = {"dem_only_preview", "lidar_dem_registration_verified"}
    if (report["mode"] not in expected or report["image_row_zero"] != "north"
            or report["vertices_per_side"] != span + 1 or span % STRIDE):
        raise ValueError("The expected first-pair terrain format is required.")
    west_e, south_n, east_e, north_n = report["pair_grid_bounds_m"]
    origin_e, origin_n = manifest["origin_grid_m_en"]
    bounds = west_e - origin_e, south_n - origin_n, east_e - origin_e, north_n - origin_n
    if not math.isclose(bounds[2] - bounds[0], 2 * span) or not math.isclose(bounds[3] - bounds[1], span):
        raise ValueError("The first-pair bounds differ from the vertex grid.")
    tiles = []
    for row in report["tiles"]:
        if Path(row["heightmap"]).name != row["heightmap"]:
            raise ValueError("Heightmap names must be relative to the terrain package.")
        path = directory / row["heightmap"]
        if digest(path) != row["heightmap_sha256"]:
            raise ValueError(f"Terrain hash differs from the report: {path.name}.")
        tiles.append(np.fromfile(path, dtype="<u2").reshape(span + 1, span + 1))
    if len(tiles) != 2 or not np.array_equal(tiles[0][:, -1], tiles[1][:, 0]):
        raise ValueError("The first pair must share an identical elevation edge.")
    heights = np.concatenate((tiles[0], tiles[1][:, 1:]), axis=1)[::STRIDE, ::STRIDE].astype(np.float64)
    heights = (heights - grid["height_code_zero"]) / grid["height_codes_per_m"] + grid["origin_navd88_m"]
    return Surface(heights, bounds, STRIDE * grid["sample_spacing_m"])


class Obj:
    def __init__(self, material_library="RVA_Pilot.mtl"):
        self.lines = ["# RVA pilot overview in meters. X east, Y north, Z up.", "mtllib " + material_library]
        self.vertices = 0
        self.faces = 0

    def group(self, name):
        self.lines.append("o " + name)

    def vertex(self, location):
        self.vertices += 1
        self.lines.append("v {:.4f} {:.4f} {:.4f}".format(*location))
        return self.vertices

    def face(self, indices):
        self.faces += 1
        self.lines.append("f " + " ".join(map(str, indices)))

    def material(self, name):
        self.lines.append("usemtl " + name)


def landscape(obj, surface):
    obj.group("Terrain")
    obj.material("terrain")
    west, _, _, north = surface.bounds
    rows, cols = surface.elevations.shape
    first = obj.vertices + 1
    for row in range(rows):
        for col in range(cols):
            obj.vertex((west + col * surface.step, north - row * surface.step, surface.elevations[row, col]))
    for row in range(rows - 1):
        for col in range(cols - 1):
            nw = first + row * cols + col
            sw = nw + cols
            obj.face((nw, sw, sw + 1))
            obj.face((nw, sw + 1, nw + 1))


def transport(obj, surface, graph):
    nodes = {row["id"]: row["local_en_m"] for row in graph["nodes"]}
    counts = {"ordinary_road_edges": 0, "foot_only_edges": 0, "grade_separated_edges_omitted": 0}
    clip = surface.footprint
    obj.group("Roads_and_paths")
    for edge in graph["edges"]:
        line = LineString((nodes[edge["a"]], nodes[edge["b"]])).intersection(clip)
        if line.geom_type != "LineString" or line.length <= 0:
            continue
        if edge["bridge"] or edge["tunnel"] or edge["layer"] != 0:
            counts["grade_separated_edges_omitted"] += 1
            continue
        car = "car" in edge["forward"] + edge["backward"]
        width = ROAD_WIDTH_M.get(edge["highway"], 5.7) if car else 1.55
        key = "ordinary_road_edges" if car else "foot_only_edges"
        obj.material("asphalt" if car else "path")
        (ax, ay), (bx, by) = line.coords
        length = math.hypot(bx - ax, by - ay)
        ox, oy = -(by - ay) * width / (2 * length), (bx - ax) * width / (2 * length)
        divisions = math.ceil(length / surface.step)
        a, b = None, None
        w, s, e, n = surface.bounds
        for i in range(divisions + 1):
            d = i / divisions
            x, y = ax + d * (bx - ax), ay + d * (by - ay)
            sides = [(min(e, max(w, x + ox)), min(n, max(s, y + oy))),
                     (min(e, max(w, x - ox)), min(n, max(s, y - oy)))]
            c, h = (obj.vertex((px, py, surface.height(px, py) + (0.12 if car else 0.18))) for px, py in sides)
            if i:
                obj.face((a, b, h, c))
            a, b = c, h
        counts[key] += 1
    return counts


def massing(obj, surface, records):
    counts = {"extruded_buildings": 0, "unresolved_or_invalid_buildings_omitted": 0}
    for row in records:
        height = row["relative_height_m"]
        if height is None:
            counts["unresolved_or_invalid_buildings_omitted"] += 1
            continue
        model = shapely.orient_polygons(scale(shape(row["footprint_unreal_xy_cm"]), xfact=0.01, yfact=-0.01,
                                             origin=(0, 0)))
        reference = row["position_local_en_m"]
        roof_z = surface.height(*reference) + height
        parts = list(shapely.get_parts(model))
        rings = [list(ring.coords)[:-1] for part in parts for ring in (part.exterior, *part.interiors)]
        elevations = {(x, y): float(surface.height(x, y)) for ring in rings for x, y in ring}
        if not elevations or roof_z <= max(elevations.values()) + 0.5:
            counts["unresolved_or_invalid_buildings_omitted"] += 1
            continue
        obj.group("Building_" + row["id"].replace("/", "_"))
        obj.material("brick")
        top = {xy: obj.vertex((*xy, roof_z)) for xy in elevations}
        bottom = {xy: obj.vertex((*xy, z - 0.18)) for xy, z in elevations.items()}
        for ring in rings:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                obj.face((bottom[a], bottom[b], top[b], top[a]))
        obj.material("slate")
        for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(model)):
            corners = list(shapely.orient_polygons(triangle).exterior.coords)[:-1]
            obj.face(tuple(top[xy] for xy in corners))
        counts["extruded_buildings"] += 1
    return counts


def export(args):
    grid = load_json(ROOT / "pilot/grid.json")
    manifest = load_json(ROOT / "pilot/tile_manifest.json")
    surface = load_surface(args.terrain, grid, manifest)
    street_graph = load_json(args.streets)
    building_data = load_json(args.buildings)
    if (street_graph["horizontal_crs"] != grid["horizontal_crs"]
            or street_graph["origin_grid_en_m"] != manifest["origin_grid_m_en"]
            or building_data["horizontal_crs"] != grid["horizontal_crs"]
            or street_graph["source"]["sha256"] != building_data["osm_source"]["sha256"]):
        raise ValueError("The street and footprint exports must share the locked pilot frame and OSM capture.")
    if args.output.resolve().is_relative_to((ROOT / "inputs").resolve()) or args.output.resolve().is_relative_to(
            args.terrain.resolve()):
        raise ValueError("Use a separate destination for the scene preview.")
    obj = Obj()
    landscape(obj, surface)
    road_counts = transport(obj, surface, street_graph)
    building_counts = massing(obj, surface, building_data["footprints"])
    if not (road_counts["ordinary_road_edges"] and building_counts["extruded_buildings"]):
        raise ValueError("Expected populated road and building layers in the first pair.")
    mesh = args.output / "RVA_Pilot.obj"
    materials = "\n\n".join(f"newmtl {name}\nKd {r} {g} {b}\nKs 0.10 0.10 0.10\nNs 18"
                              for name, (r, g, b) in MATERIALS.items())
    write_text(args.output / "RVA_Pilot.mtl", materials + "\n")
    write_text(mesh, "\n".join(obj.lines) + "\n")
    report = {"bounds_local_en_m": surface.bounds, "terrain_sample_spacing_m": surface.step,
              "vertices": obj.vertices, "faces": obj.faces, **road_counts, **building_counts,
              "mesh_sha256": digest(mesh), "street_graph_sha256": digest(args.streets),
              "building_export_sha256": digest(args.buildings),
              "terrain_report_sha256": digest(args.terrain / "terrain_first_pair.json"),
              "attribution": street_graph["attribution"]}
    write_json(args.output / "pilot_mesh_preview.json", report)
    write_json(ROOT / "reports/pilot_mesh_preview.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain", type=Path, default=ROOT / "outputs/terrain-first-pair-dem-preview")
    parser.add_argument("--streets", type=Path, default=ROOT / "outputs/pilot_street_graph.json")
    parser.add_argument("--buildings", type=Path, default=ROOT / "outputs/pilot_building_heights.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/pilot-mesh-preview")
    args = parser.parse_args()
    if shapely is None:
        print("BLOCKED: Install requirements-gis.txt before building the preview.", file=sys.stderr)
        return 3
    try:
        report = export(args)
    except FileNotFoundError as error:
        print(f"BLOCKED: Missing input {error.filename}.", file=sys.stderr)
        return 3
    except (KeyError, ValueError, OSError, shapely.errors.GEOSException) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f'PASS: Combined {report["vertices"]} vertices and {report["extruded_buildings"]} building volumes.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
