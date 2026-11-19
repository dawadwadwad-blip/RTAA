"""Build the Main Street Station headhouse in its surveyed landmark preview frame."""

from math import copysign, cos, pi, sin, tau
from random import Random

import bmesh
import bpy
from mathutils import Matrix, Vector

from station_surfaces import station_materials


# Front-left corner and front-right direction of the legacy FBX's headhouse.
# The locked FBX supplies the location and bearing; the HABS record guides the dress.
FRONT_LEFT = Vector((-356.79, -159.42, -3.95))
FRONT_RIGHT = Vector((-333.07, -177.12, -3.95))
WIDTH = 29.6
DEPTH = 23.9
EAVE = 13.4
ARCADE = (8.42, 12.07, 15.72, 19.37, 23.02)
BAY = (ARCADE[-1] - ARCADE[0]) / (len(ARCADE) - 1)
ARCADE_LEFT = ARCADE[0] - BAY / 2
ARCADE_RIGHT = ARCADE[-1] + BAY / 2
STAIR_LEFT, STAIR_RIGHT = 5.95, 25.49


def station_frame(legacy):
    right = (FRONT_RIGHT - FRONT_LEFT).normalized()
    back = Vector((-right.y, right.x, 0))
    basis = Matrix((right, back, Vector((0, 0, 1)))).transposed().to_4x4()
    return legacy.matrix_world @ Matrix.Translation(FRONT_LEFT) @ basis


class MeshGroup:
    """Batch small architectural elements into one UV-mapped mesh per assembly."""

    def __init__(self, materials):
        self.materials = materials
        self.vertices = []
        self.faces = []
        self.surface_keys = []

    def shape(self, vertices, faces, surface):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset + index for index in face) for face in faces)
        self.surface_keys.extend([surface] * len(faces))

    def prism(self, front, back, surface):
        n = len(front)
        sides = [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
        self.shape([*front, *back], [tuple(reversed(range(n))), tuple(range(n, 2 * n)), *sides], surface)

    def box(self, x0, x1, y0, y1, z0, z1, surface):
        base = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        self.prism(base, [(x, y, z1) for x, y, _ in base], surface)

    def section(self, polygon, front, back, surface):
        self.prism([(x, front, z) for x, z in polygon], [(x, back, z) for x, z in polygon], surface)

    def loft(self, profiles, surface):
        n = len(profiles[0])
        faces = [tuple(reversed(range(n)))]
        for level in range(len(profiles) - 1):
            a, b = level * n, (level + 1) * n
            faces.extend((a + i, a + (i + 1) % n, b + (i + 1) % n, b + i) for i in range(n))
        start = (len(profiles) - 1) * n
        self.shape([p for profile in profiles for p in profile], [*faces, tuple(range(start, start + n))], surface)

    def rod(self, start, end, radius, surface, sides=8, top_radius=None):
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        tangent = axis.cross(Vector((0, 0, 1)) if abs(axis.z) < 0.85 else Vector((1, 0, 0))).normalized()
        other = axis.cross(tangent)
        ring = [cos(i * tau / sides) * tangent + sin(i * tau / sides) * other for i in range(sides)]
        self.prism([start + radius * p for p in ring],
                   [end + (radius if top_radius is None else top_radius) * p for p in ring], surface)

    def transform(self, matrix, start=0):
        for i in range(start, len(self.vertices)):
            self.vertices[i] = matrix @ Vector(self.vertices[i])

    def object(self, name, collection, frame):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        slots = {key: i for i, key in enumerate(dict.fromkeys(self.surface_keys))}
        for key in slots:
            mesh.materials.append(self.materials[key])
        for polygon, key in zip(mesh.polygons, self.surface_keys, strict=True):
            polygon.material_index = slots[key]
            if name == "MSS Clock tower" and key == "clay":
                polygon.use_smooth = True
        editable = bmesh.new()
        editable.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(editable, faces=list(editable.faces))
        bmesh.ops.triangulate(editable, faces=[face for face in editable.faces if len(face.verts) > 4])
        editable.to_mesh(mesh)
        editable.free()
        mesh.update()

        uv = mesh.uv_layers.new(name="SurfaceUV").data
        for face in mesh.polygons:
            surface = mesh.materials[face.material_index].name
            unit = 2.4 if surface == "MSS Rusticated foundation stone" else 1.92
            normal = face.normal
            if abs(normal.z) > 0.999:
                right, up = Vector((1, 0, 0)), Vector((0, 1, 0))
            else:
                right = Vector((-normal.y, normal.x, 0)).normalized()
                up = normal.cross(right)
            for loop_index in face.loop_indices:
                vertex = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                uv[loop_index].uv = (right.dot(vertex) / unit, up.dot(vertex) / unit)
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.matrix_world = frame
        return obj


def arch_points(center, width, spring, rise, count=16):
    return [(center - width / 2 * cos(pi * i / count),
             spring + rise * sin(pi * i / count)) for i in range(count + 1)]


def opening(group, center, width, base, spring, rise, trim, front, depth,
            surround="trim", infill="glass_dark", *, mullions=True):
    inner = arch_points(center, width, spring, rise)
    outer = arch_points(center, width + 2 * trim, spring, rise + trim)
    for a, b, c, d in zip(inner[:-1], inner[1:], outer[1:], outer[:-1], strict=True):
        group.section((a, b, c, d), front, front + depth, surround)
    for side in (-1, 1):
        x = center + side * width / 2
        group.box(min(x, x + side * trim), max(x, x + side * trim), front, front + depth, base, spring, surround)
    if infill:
        fill = [(center - width / 2, base), (center + width / 2, base), *reversed(inner)]
        group.section(fill, front + depth - 0.04, front + depth + 0.02, infill)
    if mullions:
        y = front + depth - 0.09
        group.box(center - 0.032, center + 0.032, y, y + 0.064, base, spring + rise, "wood")
        group.box(center - width / 2, center + width / 2, y, y + 0.064, spring - 0.05, spring + 0.035, "wood")


def arcade_wall(group, centers, width, base, spring, rise, ceiling, front, back, surface):
    for index, center in enumerate(centers):
        points = arch_points(center, width, spring, rise)
        for (x0, z0), (x1, z1) in zip(points[:-1], points[1:], strict=True):
            group.section(((x0, z0), (x1, z1), (x1, ceiling), (x0, ceiling)), front, back, surface)
        if index == 0:
            group.box(ARCADE_LEFT, center - width / 2, front, back, base, ceiling, surface)
        right = centers[index + 1] - width / 2 if index + 1 < len(centers) else ARCADE_RIGHT
        group.box(center + width / 2, right, front, back, base, ceiling, surface)


def column(group, x, y, base, top, radius):
    group.box(x - radius * 1.35, x + radius * 1.35, y - radius * 1.35, y + radius * 1.35,
              base, base + 0.17, "highlight")
    group.rod((x, y, base + 0.17), (x, y, top - 0.23), radius * 0.66, "trim", top_radius=radius * 0.57)
    group.rod((x, y, top - 0.23), (x, y, top - 0.06), radius * 0.57, "highlight", top_radius=radius)
    group.box(x - radius, x + radius, y - radius, y + radius, top - 0.06, top, "highlight")


def rail(group, left, right, y, base, height=0.76, surface="trim"):
    for z, depth in ((base, 0.19), (base + height - 0.10, 0.20)):
        group.box(left, right, y - 0.13, y + 0.13, z, z + depth, surface)
    count = max(1, int((right - left) / 0.29))
    for index in range(count):
        x = left + (right - left) * (index + 0.5) / count
        group.rod((x, y, base + 0.15), (x, y, base + height * 0.58), 0.062, "trim", 6, 0.091)
        group.rod((x, y, base + height * 0.58), (x, y, base + height), 0.091, "trim", 6, 0.053)


def rectangular_sash(group, x, y, z, width, height, frame="trim_dark"):
    half = width / 2
    group.box(x - half, x + half, y + 0.11, y + 0.14, z, z + height, "glass")
    for dx in (-half, half):
        group.box(x + dx - 0.052, x + dx + 0.052, y, y + 0.15, z, z + height, frame)
    for dz in (0, height * 0.48, height):
        group.box(x - half, x + half, y + 0.02, y + 0.15, z + dz - 0.039, z + dz + 0.039, frame)
    group.box(x - half - 0.11, x + half + 0.11, y - 0.07, y + 0.18, z - 0.095, z, frame)


def pediment(group, x, y, z, width, rise):
    arch = arch_points(x, width, z, rise)
    group.section(arch, y, y + 0.20, "trim_dark")
    for a, b in zip(arch[:-1], arch[1:], strict=True):
        group.rod((a[0], y - 0.014, a[1]), (b[0], y - 0.014, b[1]), 0.043, "trim_light", 5)
    group.box(x - width / 2 - 0.07, x + width / 2 + 0.07, y - 0.09, y + 0.22, z - 0.13, z, "trim_dark")
    group.rod((x, y + 0.01, z + 0.19), (x, y - 0.055, z + 0.19), 0.13, "trim_light", 10)


def loggia(group):
    width, spring, rise = 3.10, 7.27, 1.36
    arcade_wall(group, ARCADE, width, 4.57, spring, rise, 9.49, -0.035, 0.68, "brick")
    group.box(ARCADE_LEFT, ARCADE_RIGHT, 0.67, 3.24, 8.70, 9.50, "trim")
    group.box(ARCADE_LEFT, ARCADE_RIGHT, -0.31, 3.24, 4.30, 4.51, "pavement")
    for x in ARCADE:
        opening(group, x, width, 4.64, spring, rise, 0.15, -0.20, 0.24, "trim_dark", None, mullions=False)
        opening(group, x, width + 0.30, 4.64, spring, rise + 0.15, 0.067, -0.235, 0.24,
                "trim_light", None, mullions=False)
        # The near arch has a decorated barrel, behind it is a continuous
        # covered passage and a separate row of arched wood sash.
        ring = arch_points(x, width, spring, rise, 12)
        for a, b in zip(ring[:-1], ring[1:], strict=True):
            middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            for yy in (0.12, 0.43):
                px, pz = x + (middle[0] - x) * 0.976, middle[1] - 0.045
                group.rod((px, yy, pz + 0.079), (px, yy, pz - 0.023), 0.071, "trim_light", 6)
        opening(group, x, 2.06, 4.57, 7.39, 0.74, 0.082, 2.81, 0.32, "wood", "glass_dark")
        group.box(x - 1.03, x + 1.03, 3.025, 3.09, 6.35, 6.44, "wood")
        for dx in (-0.58, 0.58):
            group.box(x + dx - 0.038, x + dx + 0.038, 3.03, 3.09, 4.57, 7.77, "wood")
        rail(group, x - 1.55, x + 1.55, -0.19, 4.48, height=0.79)
    for i in range(6):
        column(group, ARCADE_LEFT + i * BAY, -0.12, 4.54, spring + 0.07, 0.28)
    for i in range(29):
        x = ARCADE_LEFT + i * 0.64
        group.box(x, x + 0.073, 0.68, 3.12, 8.61, 8.72, "trim_dark")
    for y in (0.75, 1.39, 2.03, 2.67, 3.11):
        group.box(ARCADE_LEFT, ARCADE_RIGHT, y, y + 0.07, 8.61, 8.72, "trim_dark")


def return_walls(group):
    for side in (-1, 1):
        start = len(group.vertices)
        for position in (4.7, 10.25, 15.6, 20.75):
            x = side * position
            opening(group, x, 1.84, 0.76, 2.82, 0.35, 0.12, -0.34, 0.25, "stone", "glass_dark")
            opening(group, x, 2.25, 4.76, 7.05, 0.94, 0.14, -0.33, 0.26, "trim_dark", "glass_dark")
            opening(group, x, 2.53, 4.76, 7.05, 1.08, 0.065, -0.35, 0.16, "trim_light", None, mullions=False)
            for dx in (-0.55, 0.55):
                group.box(x + dx - 0.027, x + dx + 0.027, -0.17, -0.08, 4.75, 7.77, "wood")
            group.box(x - 1.28, x + 1.28, -0.39, 0.03, 4.64, 4.77, "trim")
            if (side, position) == (-1, 10.25):
                pediment(group, x, -0.32, 8.20, 1.94, 0.55)
        for position in range(3, 23, 2):
            x = side * position
            rectangular_sash(group, x, -0.16, 10.11, 1.36, 1.72)
            column(group, x - 0.97, -0.11, 9.74, 12.17, 0.169)
        transform = Matrix.Translation((WIDTH if side == 1 else 0, 0, 0)) @ Matrix.Rotation(side * pi / 2, 4, "Z")
        group.transform(transform, start)


def headhouse(group):
    group.box(0, WIDTH, 1.89, DEPTH, -0.45, 4.30, "stone")
    group.box(0, WIDTH, 3.16, DEPTH, 4.30, 9.50, "brick")
    group.box(0, WIDTH, 0.20, DEPTH, 9.50, EAVE, "brick")
    for left, right in ((0, ARCADE_LEFT), (ARCADE_RIGHT, WIDTH)):
        group.box(left, right, -0.034, 1.90, -0.44, 4.30, "stone")
        group.box(left, right, -0.035, 3.18, 4.30, 9.52, "brick")
    arcade_wall(group, ARCADE, 2.76, 0.20, 2.94, 0.38, 4.20, -0.07, 1.52, "stone")
    for index, x in enumerate(ARCADE):
        opening(group, x, 2.76, 0.20, 2.94, 0.38, 0.24, -0.130, 0.14, "stone", None, mullions=False)
        opening(group, x, 2.08, 0.22, 2.59, 0.36, 0.10, 1.55, 0.27, "wood", "glass_dark")
        group.box(x - 1.06, x + 1.06, 1.72, 1.78, 1.80, 1.89, "wood")
        if index in (0, 2, 3):
            for offset in (-0.52, 0.52):
                group.box(x + offset - 0.48, x + offset + 0.48, 1.71, 1.78, 0.23, 0.79, "wood")
                group.rod((x + offset * 0.29, 1.673, 1.04), (x + offset * 0.29, 1.673, 1.27), 0.025, "bronze")
    for x in (ARCADE_LEFT + index * BAY for index in range(6)):
        group.box(x - 0.34, x + 0.34, -0.17, 0.16, 0.20, 0.67, "highlight")
        group.box(x - 0.39, x + 0.39, -0.20, 0.13, 0.61, 0.73, "highlight")
    loggia(group)
    for x in (2.72, 27.72):
        facade = -0.14 if x > 10 else -0.30
        rectangular_sash(group, x, facade - 0.10, 4.82, 1.28, 2.28)
        pediment(group, x, facade - 0.16, 7.30, 1.82, 0.54)
        group.box(x - 1.07, x + 1.07, -0.90, 0.12, 4.52, 4.70, "trim")
        rail(group, x - 1.02, x + 1.02, -0.76, 4.69, 0.54)
        opening(group, x, 2.28, 0.76, 2.83, 0.36, 0.10, facade - 0.16, 0.20, "wood", "glass")
        group.box(x - 1.14, x + 1.14, facade - 0.08, facade + 0.11, 1.74, 1.85, "wood")
    for index in range(13):
        x = 7.72 + 1.67 * index
        rectangular_sash(group, x, -0.045, 10.04, 1.26, 1.78)
        column(group, x - 0.835, -0.037, 9.65, 12.12, 0.20)
        group.rod((x, -0.003, 9.71), (x, -0.075, 9.71), 0.19, "trim_light", 12)
    return_walls(group)
    for z, height, projection, surface in (
        (4.13, 0.13, 0.25, "highlight"), (4.26, 0.17, 0.48, "highlight"),
        (9.48, 0.13, 0.14, "trim"), (9.61, 0.11, 0.20, "trim_dark"),
        (12.06, 0.14, 0.25, "trim_light"), (12.22, 0.15, 0.40, "trim"),
        (12.43, 0.14, 0.51, "trim_dark"), (12.81, 0.15, 0.65, "trim"),
        (13.04, 0.17, 0.74, "trim_dark"),
    ):
        if z < 5:
            group.box(-projection, WIDTH + projection, -projection, DEPTH + projection, z, z + height, surface)
        else:
            group.box(6.77, WIDTH + projection, -projection, DEPTH + projection, z, z + height, surface)
            group.box(-projection, 6.77, 7.85, DEPTH + projection, z, z + height, surface)
    for x in (6.52 + k * 0.45 for k in range(51)):
        group.box(x, x + 0.17, -0.55, -0.11, 12.52, 12.87, "trim")
    rail(group, 6.66, WIDTH - 0.26, -0.33, 13.35, 0.66)
    for x in (6.69, 10.6, 14.48, 18.4, 22.3, 26.22, 29.26):
        group.box(x - 0.15, x + 0.15, -0.55, -0.12, 13.36, 14.09, "trim")


def finial(group, x, y, z, height):
    profiles = ((0.0, 0.20), (0.16, 0.21), (0.28, 0.11), (0.39, 0.16), (0.52, 0.09), (1.0, 0.012))
    rings = [[(x + r * height * cos(i * tau / 10), y + r * height * sin(i * tau / 10),
               z + fraction * height) for i in range(10)] for fraction, r in profiles]
    group.loft(rings, "bronze")


def dormer(group, x, y, z, ornate):
    width, height, depth = (1.02, 2.42, 2.70) if ornate else (0.61, 1.21, 1.75)
    group.box(x - width, x + width, y, y + depth, z - 0.65, z + height, "brick")
    rectangular_sash(group, x, y - 0.175, z + 0.13, width * 1.32, height * 0.78)
    if ornate:
        for dx in (-0.84, 0.84):
            column(group, x + dx, y - 0.19, z - 0.05, z + height - 0.14, 0.155)
        group.box(x - 1.21, x + 1.21, y - 0.39, y + 0.07, z + height - 0.21, z + height, "trim_dark")
        pediment(group, x, y - 0.32, z + height + 0.03, 2.19, 0.66)
        group.box(x - 0.13, x + 0.13, y - 0.21, y + 0.02, z + height + 0.61, z + height + 0.85, "trim_light")
    lip = width + 0.13
    group.loft([
        [(x - lip, y - 0.20, z + height), (x + lip, y - 0.20, z + height),
         (x + lip, y + depth, z + height), (x - lip, y + depth, z + height)],
        [(x - 0.022, y - 0.13, z + height + width), (x + 0.022, y - 0.13, z + height + width),
         (x + 0.022, y + depth - 0.32, z + height + width), (x - 0.022, y + depth - 0.32, z + height + width)],
    ], "clay")


def tiled_roof(group):
    ridge_z = 24.65
    eave_y = 0.16
    # Seat the roof behind the parapet and the face of the clock-tower shaft.
    # A projecting front eave would otherwise cross the tower brickwork.
    group.loft([
        [(-0.49, eave_y, EAVE), (WIDTH + 0.49, eave_y, EAVE),
         (WIDTH + 0.49, DEPTH - eave_y, EAVE), (-0.49, DEPTH - eave_y, EAVE)],
        [(6.9, 11.72, ridge_z), (23.87, 11.72, ridge_z), (23.87, 12.18, ridge_z), (6.9, 12.18, ridge_z)],
    ], "clay")
    group.rod((6.9, 11.95, ridge_z + 0.09), (23.87, 11.95, ridge_z + 0.09), 0.14, "bronze")
    for x in (7.08, 23.70):
        finial(group, x, 11.95, ridge_z, 1.72)
    for reverse in (False, True):
        start = len(group.vertices)
        for centers, y, ornate in (
            ((7.27, 14.9, 22.55), 1.28, True),
            ((10.53, 18.70, 25.09), 3.52, False),
            ((9.33, 13.02, 17.08, 21.07, 24.10), 6.35, False),
        ):
            z = EAVE + (y - eave_y) * (ridge_z - EAVE) / (11.72 - eave_y)
            for x in centers:
                dormer(group, x, y, z, ornate)
        if reverse:
            group.transform(Matrix.Translation((WIDTH, DEPTH, 0)) @ Matrix.Rotation(pi, 4, "Z"), start)
    group.box(28.73, 29.64, 3.50, 5.02, 10.75, 20.82, "brick")
    group.box(28.61, 29.77, 3.35, 5.16, 18.30, 18.53, "trim")
    group.box(28.56, 29.82, 3.29, 5.22, 20.70, 20.96, "trim_dark")
    for y in (3.68, 4.15, 4.64):
        group.box(28.94, 29.42, y, y + 0.22, 20.96, 21.16, "brick")
    group.rod((28.75, 4.24, 18.43), (26.74, 4.24, 18.27), 0.042, "steel")


def clock_dial(group, front, center):
    group.rod((0, front, center), (0, front - 0.16, center), 1.81, "trim_dark", 48)
    group.rod((0, front - 0.16, center), (0, front - 0.22, center), 1.63, "metal", 48)
    group.rod((0, front - 0.22, center), (0, front - 0.26, center), 1.54, "clock", 48)
    y = front - 0.28
    for number, roman in enumerate(("XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI")):
        angle = number * tau / 12
        dx, dz = sin(angle), cos(angle)
        group.rod((1.04 * dx, y, center + 1.04 * dz), (1.50 * dx, y, center + 1.50 * dz), 0.019, "metal", 5)
        strokes = {"I": (((0, -1), (0, 1)),), "V": (((-1, 1), (0, -1)), ((0, -1), (1, 1))),
                   "X": (((-1, 1), (1, -1)), ((1, 1), (-1, -1)))}
        for i, letter in enumerate(roman):
            cx = dx * 1.22 + (i - (len(roman) - 1) / 2) * 0.10
            cz = center + dz * 1.22
            for a, b in strokes[letter]:
                group.rod((cx + a[0] * 0.042, y - 0.018, cz + a[1] * 0.093),
                          (cx + b[0] * 0.042, y - 0.018, cz + b[1] * 0.093), 0.013, "metal", 5)
    for angle, length, radius in ((-pi / 3, 0.88, 0.072), (pi / 3, 1.20, 0.048)):
        group.rod((0, y - 0.09, center),
                  (length * sin(angle), y - 0.09, center + length * cos(angle)), radius, "metal", 9, 0.016)
    group.rod((0, y, center), (0, y - 0.13, center), 0.089, "metal", 12)


def clock_tower(group):
    x, y = 2.99, 3.84
    for z0, z1, radius, surface in ((-0.45, 4.23, 3.86, "stone"), (4.23, 20.22, 3.83, "brick"),
                                     (20.22, 26.25, 3.55, "brick")):
        group.box(x - radius, x + radius, y - radius, y + radius, z0, z1, surface)
    for z, height, radius, surface in (
        (4.18, 0.22, 4.0, "highlight"), (19.25, 0.17, 3.99, "trim_dark"), (19.43, 0.21, 4.18, "trim"),
        (19.74, 0.24, 4.31, "trim_dark"), (20.03, 0.28, 4.37, "trim_light"), (20.32, 0.10, 4.18, "trim_dark"),
        (25.70, 0.19, 3.91, "trim_dark"), (25.91, 0.17, 4.04, "trim"), (26.05, 0.22, 4.15, "trim_dark"),
    ):
        group.box(x - radius, x + radius, y - radius, y + radius, z, z + height, surface)
    for side in range(4):
        start = len(group.vertices)
        for offset in (-3.13, -2.69, 2.69, 3.13):
            column(group, offset, -3.64, 20.38, 25.78, 0.245)
        for index in range(11):
            dx = -3.25 + 0.65 * index
            group.section(((dx - 0.11, 18.34), (dx + 0.11, 18.34),
                           (dx + 0.22, 19.75), (dx - 0.22, 19.75)), -4.07, -3.74, "trim_dark")
            group.rod((dx, -3.87, 18.4), (dx, -4.18, 19.60), 0.125, "trim", 7, 0.151)
        for z, height, centers in ((8.17, 2.01, (-0.59, 0.59)), (11.54, 2.07, (-0.59, 0.59)),
                                    (15.55, 2.50, (-1.13, 0, 1.13))):
            group.box(centers[0] - 0.50, centers[-1] + 0.50, -4.10, -3.79, z - 0.11, z, "trim")
            for dx in centers:
                rectangular_sash(group, dx, -4.00, z, 0.81, height)
        clock_dial(group, -3.57, 23.04)
        pediment(group, 0, -3.69, 24.84, 3.08, 0.57)
        group.transform(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(side * pi / 2, 4, "Z"), start)

    rings = []
    for index in range(13):
        angle = (pi / 2 - 0.045) * index / 12
        r, z = 3.58 * cos(angle), 26.25 + 3.62 * sin(angle)
        rings.append([(x + r * copysign(abs(cos(a)) ** 0.62, cos(a)),
                       y + r * copysign(abs(sin(a)) ** 0.62, sin(a)), z)
                      for a in (i * tau / 44 for i in range(44))])
    group.loft(rings, "clay")
    finial(group, x, y, 29.77, 1.81)


def forecourt(group):
    group.box(-5.3, 33.0, -6.12, 0.9, -0.38, 0.22, "pavers")
    for left, right in ((-5.3, STAIR_LEFT), (STAIR_RIGHT, 33.0)):
        group.box(left, right, -6.42, -5.96, -2.96, 0.34, "stone")
        group.box(left - 0.08, right + 0.08, -6.55, -5.88, 0.34, 0.47, "highlight")
        for x in (left + 0.32, right - 0.32):
            group.box(x - 0.30, x + 0.30, -6.47, -5.90, -2.96, 0.78, "stone")
            group.box(x - 0.35, x + 0.35, -6.52, -5.85, 0.78, 0.90, "highlight")
    for index in range(15):
        y = -10.36 + 0.283 * index
        top = -2.58 + 0.200 * index
        group.box(STAIR_LEFT, STAIR_RIGHT, y, y + 0.288, -2.96, top, "pavement")
        group.box(STAIR_LEFT - 0.012, STAIR_RIGHT + 0.012, y - 0.016, y + 0.038,
                  top - 0.028, top + 0.005, "pavement")
    for x in (6.28, 11.26, 16.22, 21.16, 25.14):
        group.rod((x, -10.15, -1.78), (x, -6.20, 1.14), 0.029, "metal")
        for index in range(5):
            group.rod((x, -10.08 + index * 0.90, -2.41 + index * 0.64),
                      (x, -10.08 + index * 0.90, -1.73 + index * 0.66), 0.019, "metal")
    # The sidewalk apron slopes along Main Street (west end higher, east lower).
    left, right = -6.1, 33.9
    for near, far, surface in ((-11.26, -10.28, "pavers"), (-11.47, -11.24, "pavement")):
        top = [(left, near, -2.48), (right, near, -2.76), (right, far, -2.76), (left, far, -2.48)]
        group.prism([(x, y, z - 0.21) for x, y, z in top], top, surface)
    for x in (5.4, 26.1):
        y = -4.36
        group.rod((x, y, 0.17), (x, y, 0.60), 0.16, "metal", 10, 0.10)
        group.rod((x, y, 0.60), (x, y, 3.10), 0.072, "metal", 10, 0.043)
        group.rod((x, y, 3.10), (x, y, 3.44), 0.14, "clock", 6, 0.22)
        group.rod((x, y, 3.44), (x, y, 3.63), 0.245, "metal", 6, 0.030)
    shrubs = Random(15)
    for left, right in ((-4.7, STAIR_LEFT - 0.40), (STAIR_RIGHT + 0.40, 32.4)):
        group.box(left, right, -5.62, -4.97, 0.215, 0.29, "soil")
        for index in range(int((right - left) / 0.43)):
            x = left + 0.30 + 0.43 * index
            for _ in range(3):
                y = shrubs.uniform(-5.56, -5.13)
                h = shrubs.uniform(0.35, 0.66)
                cx = x + shrubs.uniform(-0.19, 0.19)
                rings = []
                for z, r in ((0.29, 0.10), (0.54, 0.31), (0.78, 0.22), (1.0, 0.018)):
                    rings.append([(cx + cos(i * tau / 6) * r, y + sin(i * tau / 6) * r, 0.20 + z * h)
                                  for i in range(6)])
                group.loft(rings, shrubs.choice(("leaves", "leaves", "leaves_light")))
    group.box(25.04, 29.64, -3.91, -3.76, 0.38, 1.62, "metal")
    for x in (25.24, 29.44):
        group.rod((x, -3.84, 0.16), (x, -3.84, 1.70), 0.066, "metal")


def scene_sign(collection, frame, material):
    text = bpy.data.curves.new("Main Street Station lettering", "FONT")
    text.body = "MAIN STREET\nSTATION"
    text.align_x = "CENTER"
    text.align_y = "CENTER"
    text.space_line = 1.13
    text.size = 0.395
    text.extrude = 0.006
    text.materials.append(material)
    obj = bpy.data.objects.new(text.name, text)
    collection.objects.link(obj)
    local = Matrix.Translation((27.34, -3.924, 1.035)) @ Matrix.Rotation(pi / 2, 4, "X")
    obj.matrix_world = local
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.matrix_world = frame
    return obj


def replace_station(scene, legacy):
    from station_train_shed import train_shed

    archived_frame = station_frame(legacy)
    # Blender object transforms serialize location, rotation and scale. Publish
    # that same representable placement instead of the unsaved affine shear.
    frame = Matrix.LocRotScale(*archived_frame.decompose())
    collection = bpy.data.collections.new("Main Street Station | street detail")
    scene.collection.children.link(collection)
    materials = station_materials()
    objects = []
    for name, builder in (("Headhouse", headhouse), ("Red clay hip and dormers", tiled_roof),
                          ("Clock tower", clock_tower), ("Main Street forecourt", forecourt),
                          ("Restored train shed", train_shed)):
        group = MeshGroup(materials)
        builder(group)
        objects.append(group.object("MSS " + name, collection, frame))
    objects.append(scene_sign(collection, frame, materials["cream"]))
    bpy.data.objects.remove(legacy, do_unlink=True)
    return frame, objects
