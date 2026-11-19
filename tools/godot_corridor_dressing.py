"""Batch original street-level details around the pilot's East Main footprint meshes."""

from bisect import bisect_right
import json
from math import floor
from random import Random

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from station_headhouse import MeshGroup
from station_surfaces import material, tiled_surface


class Corridor:
    def __init__(self, path):
        self.report = json.loads((path / "corridor.json").read_text())
        e, n = self.report["origin_en"]
        tx, tn = self.report["east_axis_en"]
        self.frame = Matrix(((tx, -tn, 0, e), (tn, tx, 0, n), (0, 0, 1, 0), (0, 0, 0, 1)))
        self.inverse = self.frame.inverted()
        self.stations, self.offsets = zip(*self.report["centerline"])
        self.start, self.end = self.report["extent"]
        self.parking = []
        bpy.ops.wm.obj_import(filepath=str(path / "East_Main_Corridor.obj"), forward_axis="Y", up_axis="Z")
        self.terrain = []
        deps = bpy.context.evaluated_depsgraph_get()
        for name in ("Terrain", "Corridor_Terrain"):
            obj = bpy.context.scene.objects[name]
            self.terrain.append((obj.matrix_world.copy(), obj.matrix_world.inverted(), BVHTree.FromObject(obj, deps)))
        self.collection = bpy.context.scene.collection

    def offset(self, along):
        index = max(0, min(len(self.stations) - 2, bisect_right(self.stations, along) - 1))
        ratio = (along - self.stations[index]) / (self.stations[index + 1] - self.stations[index])
        return self.offsets[index] + ratio * (self.offsets[index + 1] - self.offsets[index])

    def includes(self, points, terrain=False):
        projected = [self.inverse @ point for point in points]
        west, east = (-155, self.end + 30) if terrain else (-270, self.end + 40)
        width = 48 if terrain else 72
        return (max(p.x for p in projected) >= west and min(p.x for p in projected) <= east
                and min(p.y for p in projected) <= width and max(p.y for p in projected) >= -width)

    def overlaps_legacy_road(self, points):
        center = self.inverse @ (sum(points, Vector()) / len(points))
        start, end = self.start + 0.1, self.end
        return start < center.x < end and abs(center.y + self.offset(center.x)) < 9.4

    def floor(self, along, left):
        start = self.frame @ Vector((along, left, 40))
        for frame, inverse, tree in self.terrain:
            hit = tree.ray_cast(inverse @ start, inverse.to_3x3() @ Vector((0, 0, -1)), 50)[0]
            if hit is not None:
                return (frame @ hit).z
        raise ValueError(f"Street detail lies outside the DEM at {along:.2f}, {left:.2f}.")

    def dress(self, selected, tree):
        colors = {
            "brick": (0.31, 0.134, 0.088), "painted": (0.59, 0.53, 0.43),
            "rose": (0.47, 0.204, 0.182), "trim": (0.67, 0.57, 0.43),
            "glass": (0.043, 0.090, 0.106), "shop": (0.072, 0.145, 0.137),
            "wood": (0.16, 0.107, 0.064), "metal": (0.09, 0.125, 0.108),
            "wire": (0.073, 0.079, 0.074), "amber": (0.77, 0.44, 0.074),
            "green": (0.078, 0.63, 0.15), "red": (0.41, 0.075, 0.060),
            "bus_blue": (0.12, 0.25, 0.51), "bus_green": (0.52, 0.78, 0.13),
            "white": (0.70, 0.74, 0.72), "tire": (0.055, 0.056, 0.052),
            "bark": (0.11, 0.075, 0.041), "leaf": (0.118, 0.20, 0.060),
            "leaf_light": (0.19, 0.29, 0.086), "sign": (0.047, 0.22, 0.11),
        }
        materials = {key: material("East Main " + key, value) for key, value in colors.items()}
        for key, palette, mortar in (
            ("brick", ((137, 74, 53), (178, 105, 80)), (124, 92, 72)),
            ("painted", ((182, 173, 154), (215, 204, 184)), (162, 152, 132)),
            ("rose", ((151, 87, 78), (192, 126, 112)), (142, 100, 85)),
        ):
            name = "East Main " + key + " masonry"
            maps = tiled_surface(name, 7, 28, palette, mortar, (0.027, 0.048), 0.72, 223)
            materials[key] = material(name, colors[key], maps=maps)
        facades = MeshGroup(materials)
        for obj in selected:
            if obj.name.startswith("Building_"):
                self.facades(facades, obj)
        street = MeshGroup(materials)
        rng = Random(42)
        junctions = [s for s, _ in self.report["intersections"].values()]
        for side in (-1, 1):
            poles = []
            for x in range(76 + 10 * (side > 0), 541, 35):
                if min(abs(x - s) for s in junctions) < 8:
                    continue
                y = side * 8.7 - self.offset(x)
                z = self.floor(x, y)
                street.rod((x, y, z + 0.21), (x, y, z + 9.6), 0.15, "wood", 7, 0.082)
                street.rod((x, y - 0.72, z + 9.35), (x, y + 0.72, z + 9.35), 0.071, "wood", 4)
                poles.append((x, y, z + 9.48))
            for a, b in zip(poles[:-1], poles[1:]):
                for delta in (-0.61, 0.0, 0.61):
                    prior = Vector(a) + Vector((0, delta, 0))
                    for t in range(1, 7):
                        frac = t / 6
                        point = Vector(a).lerp(Vector(b), frac) + Vector((0, delta, -2.5 * frac * (1 - frac)))
                        street.rod(prior, point, 0.021, "wire", 4)
                        prior = point
            for x in range(94 + side * 5, 541, 20 + (side < 0) * 16):
                if min(abs(x - s) for s in junctions) > 11:
                    y = side * 8.65 - self.offset(x)
                    tree(street, rng, x, y, self.floor(x, y) + 0.17, rng.uniform(5.8, 8.1), 6)
            for x in range(77 + 5 * (side > 0), 532, 19):
                if min(abs(x - s) for s in junctions) > 15:
                    y = side * 6.10 - self.offset(x)
                    self.park(street, x, y, 4.25, 1.48, 1.72, rng.choice(("red", "white", "bus_blue", "metal")))
        signs = []
        for name, (x, d) in self.report["intersections"].items():
            if name == "20th":
                continue
            y = -d
            z = max(self.floor(x + 4, y + 8), self.floor(x + 4, y - 5))
            self.signal(street, x + 4, y, z)
            signs.append(self.sign(name + " ST", (x + 4.16, y + 6.25, z + 6.22), materials["white"]))
        # An illustrative bus stop on the south curb opposite the station.
        x, y = 59, -6.0 - self.offset(59)
        self.park(street, x, y, 10.2, 3.03, 2.08, "bus_blue", bus=True)
        base = self.floor(x, y - 3.0)
        street.box(x - 3.7, x + 3.7, y - 4.05, y - 2.60, base + 0.08, base + 0.46, "brick")
        street.box(x - 3.8, x + 3.8, y - 4.1, y - 2.40, base + 2.56, base + 2.74, "metal")
        for s in (x - 3.3, x + 3.3):
            street.rod((s, y - 3.9, base + 0.43), (s, y - 3.9, base + 2.58), 0.082, "metal", 6)
        return signs + [facades.object("Corridor_Facade_Details", self.collection, Matrix.Identity(4)),
                        street.object("Corridor_Street_Details", self.collection, self.frame)]

    def facades(self, details, obj):
        coordinates = [obj.matrix_world @ v.co for v in obj.data.vertices]
        frame = obj.matrix_world.to_3x3()
        origin = self.inverse @ (sum(coordinates, Vector()) / len(coordinates))
        frontage = 57 < origin.x < self.end + 30 and abs(origin.y + self.offset(origin.x)) < 39
        if not frontage:
            return
        tint = ("painted" if origin.y < 0 and origin.x > 360 else
                "rose" if origin.y > 0 and origin.x < 147 else "brick")
        for i, existing in enumerate(obj.data.materials):
            if existing and existing.name.split(".")[0] == "brick":
                obj.data.materials[i] = details.materials[tint]
        uv = (obj.data.uv_layers.active or obj.data.uv_layers.new(name="Corridor masonry")).data
        for face in obj.data.polygons:
            normal = (frame @ face.normal).normalized()
            horizontal = Vector((-normal.y, normal.x, 0)).normalized()
            for loop in face.loop_indices:
                point = coordinates[obj.data.loops[loop].vertex_index]
                uv[loop].uv = (point.dot(horizontal) / 1.92, point.z / 1.92)
            if abs(normal.z) > 0.05:
                continue
            points = [coordinates[i] for i in face.vertices]
            center = self.inverse @ (sum(points, Vector()) / len(points))
            if not 64 < center.x < self.end + 20 or not 8.5 < abs(center.y + self.offset(center.x)) < 25:
                continue
            toward_road = self.frame.to_3x3() @ Vector((0, -1 if center.y > 0 else 1, 0))
            corner = min(abs(center.x - s) for s, _ in self.report["intersections"].values()) < 11
            if normal.dot(toward_road) < 0.52 and not corner:
                continue
            base, top = min(p.z for p in points), max(p.z for p in points)
            direction = Vector((-normal.y, normal.x, 0))
            lo, hi = sorted(points, key=direction.dot)[::len(points) - 1]
            length = (hi - lo).dot(direction)
            if length < 3.6 or top - base < 3.5:
                continue
            floors = min(5, max(1, round((top - base) / 3.22)))
            bays = min(18, floor(length / 2.32))
            if bays < 1:
                continue
            # The thin shell is confined to the source face so footprint dimensions stay intact.
            transform = Matrix((direction, normal, Vector((0, 0, 1)))).transposed().to_4x4()
            transform.translation = Vector((lo.x, lo.y, base))
            height = top - base
            start = len(details.vertices)
            details.box(0, length, 0.013, 0.048, 0.15, height - 0.065, tint)
            band = height / floors
            details.box(0, length, 0.037, 0.23, height - 0.27, height - 0.075, "trim")
            if not corner and 120 < center.x < 390 and floors >= 2 and int(center.x) % 3 == 0:
                x0, x1 = 0.22, length - 0.22
                details.prism([(x0, 0.10, band + 0.18), (x1, 0.10, band + 0.18),
                               (x1, 0.93, band - 0.16), (x0, 0.93, band - 0.16)],
                              [(x0, 0.10, band + 0.24), (x1, 0.10, band + 0.24),
                               (x1, 0.93, band - 0.085), (x0, 0.93, band - 0.085)], "sign")
            for level in range(floors):
                for i in range(bays):
                    x = (i + 0.5) * length / bays
                    z = band * level + (0.22 if level == 0 else 0.73)
                    half = length / bays * (0.38 if level == 0 else 0.255)
                    high = z + min(band - 0.89, 2.28 if level == 0 else 1.65)
                    details.box(x - half - 0.095, x + half + 0.095, 0.045, 0.087, z - 0.075, high + 0.09, "trim")
                    details.box(x - half, x + half, 0.084, 0.101, z, high, "shop" if level == 0 else "glass")
                    details.box(x - 0.024, x + 0.024, 0.099, 0.127, z, high, "metal")
                    if level:
                        details.box(x - half - 0.085, x + half + 0.085, 0.086, 0.202, z - 0.099, z + 0.012, "trim")
            details.transform(transform, start)

    def park(self, group, x, y, length, height, width, tint, bus=False):
        base = self.floor(x, y) + 0.14
        lo, hi = x - length / 2, x + length / 2
        hw = width / 2
        group.box(lo, hi, y - hw, y + hw, base + 0.34, base + (height - 0.9 if bus else 0.94), tint)
        if bus:
            group.box(lo + 0.12, hi - 0.12, y - hw, y + hw, base + height - 0.9, base + height - 0.28, "glass")
            group.box(lo, hi, y - hw, y + hw, base + height - 0.28, base + height, "bus_green")
        else:
            lower = [(x - 1.33, y - 0.75, base + 0.92), (x + 1.12, y - 0.75, base + 0.92),
                     (x + 1.12, y + 0.75, base + 0.92), (x - 1.33, y + 0.75, base + 0.92)]
            upper = [(x + a, y + b, base + height) for a, b in
                     ((-0.69, -0.71), (0.68, -0.71), (0.68, 0.71), (-0.69, 0.71))]
            group.prism(lower, upper, "glass")
            group.box(x - 0.73, x + 0.73, y - 0.73, y + 0.73, base + height - 0.05, base + height + 0.035, tint)
            for side in (-1, 1):
                yy = y + side * (hw - 0.24)
                group.box(lo - 0.03, lo + 0.035, yy - 0.13, yy + 0.13, base + 0.68, base + 0.81, "white")
                group.box(hi - 0.04, hi + 0.03, yy - 0.13, yy + 0.13, base + 0.64, base + 0.79, "red")
        for end in (lo + 0.78, hi - 0.78):
            for side in (-1, 1):
                group.rod((end, y + side * (hw - 0.22), base + 0.30),
                          (end, y + side * (hw + 0.045), base + 0.30), 0.30, "tire", 8)
        self.parking.append([x, -y - self.offset(x), length / 2, hw])

    def signal(self, group, x, y, z):
        group.rod((x, y + 8.65, z - 0.17), (x, y + 8.65, z + 6.38), 0.17, "metal", 8, 0.11)
        group.rod((x, y + 8.65, z + 6.38), (x, y - 5.4, z + 6.38), 0.093, "metal", 6)
        for lane in (-4.8, -0.9, 3.27):
            mid = y + lane
            group.box(x - 0.18, x + 0.19, mid - 0.16, mid + 0.16, z + 5.91, z + 6.78, "amber")
            for i, finish in enumerate(("green", "wire", "wire")):
                height = z + 6.07 + 0.27 * i
                group.rod((x + 0.18, mid, height), (x + 0.23, mid, height), 0.096, finish, 10)
        group.box(x - 0.12, x + 0.11, y + 5.30, y + 7.20, z + 6.11, z + 6.49, "sign")

    def sign(self, text, position, finish):
        label = bpy.data.curves.new(text, "FONT")
        label.body, label.size = text, 0.235
        label.align_x, label.align_y = "CENTER", "CENTER"
        label.materials.append(finish)
        obj = bpy.data.objects.new("Corridor sign " + text, label)
        self.collection.objects.link(obj)
        transform = self.frame @ Matrix.Translation(position) @ Matrix(
            ((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        bpy.context.view_layer.update()
        baked = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        bpy.data.objects.remove(obj, do_unlink=True)
        mesh = bpy.data.objects.new("Corridor sign " + text, baked)
        self.collection.objects.link(mesh)
        mesh.matrix_world = transform
        return mesh

    def gameplay(self):
        return {"east_main_centerline": self.report["centerline"], "start_at": self.report["start_at"],
                "end_at": self.end - 1, "parking": self.parking}
