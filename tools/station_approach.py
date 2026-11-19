"""Dress the East Main Street approach within the locked station preview frame."""

import math

import numpy as np
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon, box


ASPHALT = 0.065
WALK = 0.19
CURB_WIDTH = 0.18
STAIR_LEFT, STAIR_RIGHT = 5.95, 25.49
STAIR_Y, STAIR_Z = -10.365, -2.575
ROAD_WAYS = (120374950, 1366154365, 699605461)
CROSSINGS = (1306729451, 1306729447, 1257934912)
CROSSING_LABELS = ("station_crosswalk", "fifteenth_crosswalk", "fifteenth_west_crosswalk")
WEST_JOIN_X, EAST_JOIN_X = -79, 64
WALK_WAYS = (1306729434, 1306729452, 1494471794, 1494471795)
DRIVEWAY = 1148449849
EAST_STATION_WALK = 1306729456
MATERIALS = {
    "approach_asphalt": (0.105, 0.112, 0.119),
    "approach_brick": (0.39, 0.155, 0.108),
    "approach_white": (0.88, 0.86, 0.75),
    "approach_yellow": (0.90, 0.58, 0.095),
    "approach_walk": (0.52, 0.47, 0.41),
    "approach_curb": (0.65, 0.60, 0.52),
}


class Drape:
    """Split overlay faces at the terrain cell edges and the terrain diagonals."""

    def __init__(self, obj, surface):
        self.obj = obj
        self.surface = surface
        self.triangles = 0
        self.max_interpolation_error = 0.0
        self.min_clearance = math.inf

    def add(self, polygon, material, height, *, sealed=False):
        parts = [part for part in shapely.get_parts(shapely.make_valid(polygon)) if part.area > 0]
        polygon = shapely.union_all(parts, grid_size=0.0001)
        if polygon.area < 1e-8:
            return
        self.obj.material(material)
        vertices, edges = {}, {}
        west, _, _, north = self.surface.bounds
        step = self.surface.step
        rows, cols = self.surface.elevations.shape
        xmin, ymin, xmax, ymax = polygon.bounds
        for r in range(max(0, math.floor((north - ymax) / step)), min(rows - 1, math.ceil((north - ymin) / step))):
            y = north - r * step
            for c in range(max(0, math.floor((xmin - west) / step)), min(cols - 1, math.ceil((xmax - west) / step))):
                x = west + c * step
                nw, sw, se, ne = (x, y), (x, y - step), (x + step, y - step), (x + step, y)
                for corners in ((nw, sw, se), (nw, se, ne)):
                    piece = shapely.intersection(polygon, Polygon(corners), grid_size=0.0001)
                    if piece.area < 1e-8:
                        continue
                    for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(piece)):
                        ring = shapely.orient_polygons(triangle).exterior.coords
                        points = list(ring)[:-1]
                        if len(set(points)) != 3:
                            continue
                        for point in points:
                            if point not in vertices:
                                clearance = height(*point)
                                self.min_clearance = min(self.min_clearance, clearance)
                                z = self.surface.height(*point) + clearance
                                vertices[point] = self.obj.vertex((*point, z)), z
                        self.obj.face(tuple(vertices[pt][0] for pt in points))
                        self.triangles += 1
                        x_mid, y_mid = (sum(axis) / 3 for axis in zip(*points))
                        z_mid = sum(vertices[pt][1] for pt in points) / 3
                        error = z_mid - self.surface.height(x_mid, y_mid) - height(x_mid, y_mid)
                        self.max_interpolation_error = max(self.max_interpolation_error, abs(error))
                        if sealed:
                            for a, b in zip(points, points[1:] + points[:1]):
                                if (b, a) in edges:
                                    del edges[b, a]
                                else:
                                    edges[a, b] = None
        if sealed:
            # Close raised vertical edges down into the terrain. There are no exposed undersides.
            bottom = {}
            boundary = polygon.boundary
            for a, b in edges:
                if boundary.distance(LineString((a, b)).interpolate(0.5, normalized=True)) > 0.00011:
                    continue
                for point in (a, b):
                    if point not in bottom:
                        bottom[point] = self.obj.vertex((*point, self.surface.height(*point) - 0.025))
                self.obj.face((vertices[b][0], vertices[a][0], bottom[a], bottom[b]))


def offset_band(x, lower, upper):
    return Polygon(list(zip(x, lower)) + list(zip(reversed(x), reversed(upper))))


def extended_line(line, distance):
    a, b = np.asarray(line.coords[0]), np.asarray(line.coords[-1])
    heading = (b - a) / np.linalg.norm(b - a)
    return LineString([a - heading * distance, *line.coords, b + heading * distance])


class StationApproach:
    def __init__(self, graph, frame, surface):
        self.surface = surface
        self.frame = np.asarray(frame, dtype=float)
        if (self.frame.shape != (4, 4) or not np.isfinite(self.frame).all()
                or not np.allclose(self.frame[2:, :], [[0, 0, 1, self.frame[2, 3]], [0, 0, 0, 1]], atol=1e-7)
                or not np.allclose(self.frame[:2, 2], 0, atol=1e-7)
                or not np.allclose(self.frame[:2, :2].T @ self.frame[:2, :2], np.eye(2), atol=0.004)
                or np.linalg.det(self.frame[:2, :2]) <= 0):
            raise ValueError("Expected the station export's level east/north frame in meters.")
        self.to_local = np.linalg.inv(self.frame)
        self.z_origin = self.frame[2, 3]
        nodes = {node["id"]: node["local_en_m"] for node in graph["nodes"]}

        def way(*ids):
            lines = [LineString((nodes[e["a"]], nodes[e["b"]])) for e in graph["edges"]
                     if e.get("way") in ids and not (e["bridge"] or e["tunnel"] or e["layer"])]
            return self._transform(shapely.line_merge(shapely.union_all(lines)), self.to_local)

        centerline = way(*ROAD_WAYS)
        self.crossings = [way(osm_id) for osm_id in CROSSINGS]
        north_walk = way(WALK_WAYS[0])
        driveway = way(DRIVEWAY)
        east_walk = way(EAST_STATION_WALK)
        if any(line.geom_type != "LineString" or line.is_empty
               for line in [centerline, north_walk, driveway, east_walk, *self.crossings]):
            raise ValueError("The pinned station approach ways must form continuous ground paths.")
        ends = sorted([self.crossings[0].coords[0], self.crossings[0].coords[-1]], key=lambda point: point[1])
        self.crossing_width = ends[1][1] - ends[0][1]
        if not (14.0 < self.crossing_width < 15.3 and abs(ends[1][0] - 21.1) < 0.5):
            raise ValueError("The station crossing and the exported step frame do not line up.")
        self.crossing_axes = [list(zip(*sorted((y, x) for x, y in line.coords))) for line in self.crossings]

        def ordinates(line, x):
            xs, ys = zip(*sorted(line.coords))
            return np.interp(x, xs, ys)

        # Widen only at the authored approach and meet the old road at each end.
        road_x = sorted({WEST_JOIN_X, -65, -64, 51, EAST_JOIN_X,
                         *(x for x, _ in centerline.coords if WEST_JOIN_X < x < EAST_JOIN_X)})
        center_y = ordinates(centerline, road_x)
        self.road_joins = []
        for name, x, inward in (("west", WEST_JOIN_X, 1), ("east", EAST_JOIN_X, -1)):
            for side, delta in (("inside", inward * 0.25), ("outside", -inward * 0.25)):
                y = float(ordinates(centerline, x + delta))
                point = self.world(shapely.Point(x + delta, y))
                en = list(point.coords[0])
                self.road_joins.append({"name": f"{name}_join_{side}", "local_en_m": en,
                                        "z_m": float(surface.height(*en) + 0.12),
                                        "object": "East_Main_Approach_Road" if side == "inside" else "Roads_and_paths"})
        mid_y = float(ordinates(centerline, ends[1][0]))
        road_north = ends[1][1] - mid_y
        road_south = mid_y - ends[0][1]
        taper = np.interp(road_x, [WEST_JOIN_X, -65, 51, EAST_JOIN_X], [0, 1, 1, 0])
        self.x = road_x
        self.north = center_y + 4 + (road_north - 4) * taper
        self.south = center_y - 4 - (road_south - 4) * taper
        self.center = LineString(list(zip(road_x, center_y)))
        main_road = offset_band(road_x, self.south, self.north)
        self.drive_end_y = driveway.bounds[1]
        self.drive = driveway.buffer(1.8, cap_style="flat", join_style="mitre")
        self.road = main_road.union(self.drive)

        walk_x = sorted({-65.2, -6.1, 4.95, STAIR_LEFT, STAIR_RIGHT, 26.49, 33.9, 60,
                         *(x for x, _ in north_walk.coords if -65.2 < x < 60),
                         *(x for x in road_x if -65.2 < x < 60)})
        north = np.interp(walk_x, road_x, self.north)
        south = np.interp(walk_x, road_x, self.south)
        back = ordinates(north_walk, walk_x) + 0.79
        for i, x in enumerate(walk_x):
            if -6.1 <= x <= 33.9:
                back[i] = STAIR_Y
        self.north_walk = offset_band(walk_x, north + CURB_WIDTH, back)
        self.south_walk = offset_band(walk_x, south - 2.12, south - CURB_WIDTH).difference(self.drive)
        self.north_curb = offset_band(walk_x, north, north + CURB_WIDTH)
        self.south_curb = offset_band(walk_x, south - CURB_WIDTH, south).difference(self.drive)
        self.east_walk = east_walk.buffer(0.79, cap_style="flat", join_style="mitre")
        # The shape already covers the crossing ribbons, the mapped sidewalk connector and the driveway.
        combined = shapely.union_all([self.road, self.north_walk, self.south_walk, self.north_curb, self.south_curb,
                                      self.east_walk])
        self.replacement = self.world(combined.buffer(0.0001))
        self.drive_replacement = self.replacement.union(self.world(self.drive.buffer(0.05)))
        self.east_walk_replacement = self.replacement.union(self.world(self.east_walk.buffer(0.05)))
        self.walk_replacement = self.replacement.union(self.world(box(-65.2, -31, 60, -6.8)))
        self.stair_replacement = self.world(box(4.0, -11, 27.0, -3.4))
        landing = self.world(box(STAIR_LEFT, STAIR_Y - 0.001, STAIR_RIGHT, STAIR_Y))
        if not surface.footprint.covers(self.replacement) or not self.replacement.covers(landing):
            raise ValueError("The station approach must cover the lowest step and fit inside the terrain pair.")

    @staticmethod
    def _transform(geometry, frame):
        a, b, _, x = frame[0]
        d, e, _, y = frame[1]
        return affine_transform(geometry, [a, b, d, e, x, y])

    def world(self, geometry):
        return self._transform(geometry, self.frame)

    def legacy_mask(self, way):
        if way in (*WALK_WAYS, *CROSSINGS):
            return self.walk_replacement
        if way == 1306729442:
            return self.stair_replacement
        if way == DRIVEWAY:
            return self.drive_replacement
        if way == EAST_STATION_WALK:
            return self.east_walk_replacement
        return self.replacement

    def walk_height(self, east, north, side):
        a, b = self.to_local[:2]
        x, y = a[0] * east + a[1] * north + a[3], b[0] * east + b[1] * north + b[3]
        curb = np.interp(x, self.x, self.north if side > 0 else self.south)
        across = max(0, side * (y - curb))
        # Lower the full curb within each crosswalk, then blend back to the raised pavement.
        ramp = min(np.clip((abs(x - np.interp(y, *axis)) - 1.50) / 0.85, 0, 1)
                   for axis in self.crossing_axes)
        lift = ASPHALT + (WALK - ASPHALT) * max(ramp, min(1, across / 1.30))
        if side < 0 and 30 < x < 37:
            lift = ASPHALT + min(1, self.drive.distance(shapely.Point(x, y)) / 0.65) * (lift - ASPHALT)
        if side > 0:
            along = min(1, max(0, x - (STAIR_LEFT - 1)), max(0, STAIR_RIGHT + 1 - x))
            weight = along * np.clip(1 + (y - STAIR_Y) / 1.50, 0, 1)
            tread = self.z_origin + STAIR_Z - self.surface.height(east, north)
            lift += weight * (tread - lift)
        return lift

    def asphalt_height(self, east, north):
        a, b = self.to_local[:2]
        x, y = a[0] * east + a[1] * north + a[3], b[0] * east + b[1] * north + b[3]
        # The previous road and driveway surfaces use a 0.12 m ground offset.
        join = max(np.clip((WEST_JOIN_X + 4 - x) / 4, 0, 1), np.clip((x - EAST_JOIN_X + 4) / 4, 0, 1),
                   np.clip((self.drive_end_y + 1.5 - y) / 1.5, 0, 1))
        return ASPHALT + join * (0.12 - ASPHALT)

    def add(self, obj):
        drape = Drape(obj, self.surface)
        brick, white = [], []
        for index, line in enumerate(self.crossings):
            corridor = extended_line(line, 1.0).buffer(1.46, cap_style="flat").intersection(self.road)
            inner = extended_line(line, 1.0).buffer(1.23, cap_style="flat").intersection(self.road)
            white.append(corridor.difference(inner))
            if index == 0:
                brick.append(inner)
        brick, white = shapely.union_all(brick), shapely.union_all(white)
        double_line = [self.center.offset_curve(d).buffer(0.055, cap_style="flat") for d in (-0.16, 0.16)]
        ends = box(-61, -30, 49, -10)
        yield_area = shapely.union_all([extended_line(line, 1.0).buffer(2.1) for line in self.crossings])
        yellow = shapely.union_all(double_line).intersection(ends).difference(yield_area)
        pavement = self.road.difference(shapely.union_all([brick, white, yellow]))
        obj.group("East_Main_Approach_Road")
        for polygon, material in ((pavement, "approach_asphalt"), (brick, "approach_brick"),
                                  (white, "approach_white"), (yellow, "approach_yellow")):
            drape.add(self.world(polygon), material, self.asphalt_height, sealed=material == "approach_asphalt")
        road_triangles, road_error = drape.triangles, drape.max_interpolation_error
        for name, walk, curb, side in (("North", self.north_walk, self.north_curb, 1),
                                      ("South", self.south_walk, self.south_curb, -1)):
            obj.group(f"East_Main_Approach_{name}_Walk")
            # Break at the authored grade changes so the stair lip and ramp edges are explicit.
            cuts = sorted({walk.bounds[0], walk.bounds[2], 4.95, STAIR_LEFT, STAIR_RIGHT, 26.49,
                           *(line.interpolate(0.5, normalized=True).x + d
                             for line in self.crossings for d in (-2.33, -1.48, 1.48, 2.33))})
            for left, right in zip(cuts, cuts[1:]):
                strip = box(left, -40, right, 0)
                for polygon, material in ((walk, "approach_walk"), (curb, "approach_curb")):
                    drape.add(self.world(polygon.intersection(strip)), material,
                              lambda e, n: self.walk_height(e, n, side), sealed=True)
        obj.group("East_Main_Approach_East_Station_Walk")
        drape.add(self.world(self.east_walk), "approach_walk", lambda _x, _y: 0.09, sealed=True)
        if drape.min_clearance < 0.025:
            raise ValueError("The authored approach surfaces must remain above the preview terrain.")
        witnesses = []

        def witness(name, group, point, height):
            e, n = self.world(shapely.Point(*point)).coords[0]
            witnesses.append({"name": name, "object": group, "local_en_m": [e, n],
                              "z_m": float(self.surface.height(e, n) + height(e, n))})

        for label, line in zip(CROSSING_LABELS, self.crossings):
            witness(label, "East_Main_Approach_Road", line.intersection(self.center).coords[0], self.asphalt_height)
        for x in (6.15, 13.77, 21.17, 25.29):
            witness(f"bottom_stair_{x}", "East_Main_Approach_North_Walk", (x, STAIR_Y - 0.002),
                    lambda e, n: self.walk_height(e, n, 1))
        for x in (-61.0, -42.0, 0.0, 11.0, 39.0, 55.0):
            for side, way_side in ((1, "North"), (-1, "South")):
                boundary = np.interp(x, self.x, self.north if side > 0 else self.south)
                witness(f"{way_side.lower()}_curb_{x}", f"East_Main_Approach_{way_side}_Walk",
                        (x, boundary + side * 0.09), lambda e, n: self.walk_height(e, n, side))
        return {"schema_version": 1, "station_frame": self.frame.tolist(), "road_ways": ROAD_WAYS,
                "crosswalk_ways": CROSSINGS, "station_crossing_span_m": round(self.crossing_width, 3),
                "road_triangles": road_triangles, "walk_and_curb_triangles": drape.triangles - road_triangles,
                "max_road_interpolation_error_m": round(road_error, 6),
                "max_walk_interpolation_error_m": round(drape.max_interpolation_error, 6),
                "min_authored_vertex_clearance_m": round(drape.min_clearance, 6), "witnesses": witnesses,
                "road_joins": self.road_joins}
