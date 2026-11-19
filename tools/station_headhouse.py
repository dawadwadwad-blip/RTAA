"""Build the Main Street Station headhouse in its surveyed landmark preview frame."""

from math import cos, pi, sin, sqrt, tau
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
ARCADE = (8.1, 12.1, 16.1, 20.1, 24.1)


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
            unit = 2.4 if surface == "MSS Rusticated granite" else 1.92
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
    return [(center + width * i / count - width / 2,
             spring + rise * sqrt(max(0, 1 - (2 * i / count - 1)**2))) for i in range(count + 1)]


def opening(group, center, width, base, spring, rise, trim, front, depth,
            surround="trim", infill="glass_dark", joints=False, mullions=True):
    inner = arch_points(center, width, spring, rise)
    outer = arch_points(center, width + 2 * trim, spring, rise + trim)
    for index, (a, b, c, d) in enumerate(zip(inner[:-1], inner[1:], outer[1:], outer[:-1], strict=True)):
        surface = "highlight" if joints and index in (3, 8, 12) else surround
        group.section((a, b, c, d), front, front + depth, surface)
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
        left = center - 2
        if index == 0:
            group.box(left, center - width / 2, front, back, base, ceiling, surface)
        right = centers[index + 1] - width / 2 if index + 1 < len(centers) else center + 2
        group.box(center + width / 2, right, front, back, base, ceiling, surface)


def column(group, x, y, base, top, radius):
    group.box(x - radius * 1.35, x + radius * 1.35, y - radius * 1.35, y + radius * 1.35,
              base, base + 0.17, "highlight")
    group.rod((x, y, base + 0.17), (x, y, top - 0.23), radius * 0.66, "trim", top_radius=radius * 0.57)
    group.rod((x, y, top - 0.23), (x, y, top - 0.06), radius * 0.57, "highlight", top_radius=radius)
    group.box(x - radius, x + radius, y - radius, y + radius, top - 0.06, top, "highlight")


def rail(group, left, right, y, base, height=0.76):
    for z, depth in ((base, 0.19), (base + height - 0.10, 0.20)):
        group.box(left, right, y - 0.13, y + 0.13, z, z + depth, "highlight")
    count = max(1, int((right - left) / 0.29))
    for index in range(count):
        x = left + (right - left) * (index + 0.5) / count
        group.rod((x, y, base + 0.15), (x, y, base + height * 0.58), 0.062, "trim", 6, 0.091)
        group.rod((x, y, base + height * 0.58), (x, y, base + height), 0.091, "trim", 6, 0.053)


def sash(group, x, y, z, width=1.15, height=1.67):
    opening(group, x, width, z, z + height - 0.22, 0.22, 0.10, y, 0.24)
    group.box(x - width / 2 - 0.18, x + width / 2 + 0.18, y - 0.07, y + 0.2, z - 0.10, z, "highlight")
    group.box(x - width / 2, x + width / 2, y + 0.13, y + 0.22, z + height * 0.51, z + height * 0.51 + 0.055, "wood")


def headhouse(group):
    group.box(0, WIDTH, 1.24, DEPTH, -0.45, 4.3, "stone")
    group.box(0, WIDTH, 0.62, DEPTH, 4.3, EAVE, "brick")
    group.box(0, 6.1, -0.10, 1.25, -0.44, 4.3, "stone")
    group.box(26.1, WIDTH, -0.10, 1.25, -0.44, 4.3, "stone")
    arcade_wall(group, ARCADE, 3.00, 0.20, 2.62, 0.66, 4.18, -0.03, 1.07, "stone")
    for index, x in enumerate(ARCADE):
        opening(group, x, 3.00, 0.20, 2.62, 0.66, 0.24, -0.20, 0.24, "highlight", None, True, False)
        opening(group, x, 1.96, 0.23, 2.49, 0.37, 0.09, 0.90, 0.20, "wood", "glass_dark")
        if index in (0, 2, 3):
            for offset in (-0.52, 0.52):
                group.box(x + offset - 0.49, x + offset + 0.49, 1.05, 1.14, 0.24, 0.92, "wood")
                group.rod((x + offset * 0.32, 1.01, 1.16), (x + offset * 0.32, 1.01, 1.38), 0.032, "bronze")
        opening(group, x, 3.04, 4.81, 7.89, 1.04, 0.19, -0.30, 0.92, "trim", "glass", True)
        for offset in (-0.76, 0.76):
            group.box(x + offset - 0.025, x + offset + 0.025, 0.53, 0.62, 4.96, 8.6, "wood")
        rail(group, x - 1.55, x + 1.55, -0.41, 4.53)
        group.box(x - 0.19, x + 0.19, -0.54, -0.21, 8.69, 9.13, "highlight")
        for offset in (-1.36, 1.36):
            medallion = x + offset
            group.rod((medallion, -0.12, 8.76), (medallion, -0.21, 8.76), 0.13, "trim", 12)
            for petal in range(5):
                angle = petal * tau / 5
                px, pz = medallion + 0.068 * cos(angle), 8.76 + 0.068 * sin(angle)
                group.rod((px, -0.21, pz), (px, -0.25, pz), 0.042, "highlight", 6)
    arcade_wall(group, ARCADE, 3.04, 4.72, 7.89, 1.04, 9.45, -0.10, 0.59, "brick")
    for index in range(6):
        column(group, 6.1 + index * 4, -0.28, 4.48, 8.02, 0.28)
    sash(group, 27.95, -0.24, 4.97, 1.56, 3.44)
    group.box(26.73, 29.27, -0.94, 0.24, 4.56, 4.85, "highlight")
    rail(group, 26.78, 29.22, -0.84, 4.8)
    for index in range(13):
        x = 6.80 + 1.77 * index
        sash(group, x, 0.36, 10.10)
        column(group, x - 0.83, 0.24, 9.92, 12.07, 0.17)
    for y in (4.3, 11.2, 18.1):
        for side in (-1, 1):
            start = len(group.vertices)
            for z, width, height in ((1.03, 1.45, 2.31), (5.0, 2.28, 3.64), (10.12, 1.65, 1.68)):
                sash(group, y * -side, 0.29, z, width, height)
            transform = Matrix.Translation((WIDTH if side == 1 else 0, 0, 0)) @ Matrix.Rotation(-side * pi / 2, 4, "Z")
            group.transform(transform, start)
    for z, height, projection in ((4.16, 0.15, 0.28), (4.39, 0.27, 0.47), (9.65, 0.25, 0.31),
                                  (12.18, 0.19, 0.27), (12.88, 0.32, 0.49), (13.23, 0.19, 0.65)):
        group.box(-projection, WIDTH + projection, -projection, DEPTH + projection, z, z + height, "highlight")
    for x in (6.17 + k * 0.47 for k in range(50)):
        group.box(x, x + 0.22, -0.48, -0.12, 12.6, 12.92, "trim")
    rail(group, 6.66, WIDTH - 0.26, -0.33, 13.35, 0.66)
    for x in (6.69, 10.6, 14.48, 18.4, 22.3, 26.22, 29.26):
        group.box(x - 0.15, x + 0.15, -0.55, -0.12, 13.36, 14.09, "trim")
    for x in (6.85, 29.34):
        group.rod((x, -0.44, 0.31), (x, -0.44, 12.53), 0.048, "bronze", 8)
        for z in (2.9, 5.1, 8.1, 10.8):
            group.rod((x, -0.44, z), (x, -0.44, z + 0.075), 0.062, "metal", 8)


def tiled_roof(group):
    group.loft([
        [(-0.46, -0.51, EAVE), (WIDTH + 0.44, -0.51, EAVE), (WIDTH + 0.44, DEPTH + 0.48, EAVE), (-0.46, DEPTH + 0.48, EAVE)],
        [(6.5, 11.1, 22.6), (23.1, 11.1, 22.6), (23.1, 12.4, 22.6), (6.5, 12.4, 22.6)],
    ], "clay")
    group.rod((6.5, 11.75, 22.72), (23.1, 11.75, 22.72), 0.13, "trim")
    for x in (6.62, 22.98):
        group.rod((x, 11.75, 22.63), (x, 11.75, 23.55), 0.12, "bronze", 10, 0.018)

    for centers, y, size in ((ARCADE + (28.0,), 2.30, 1.0), ((10.2, 14.2, 18.2, 22.2), 6.65, 0.68)):
        for index, x in enumerate(centers):
            z = EAVE + (y + 0.51) * (22.6 - EAVE) / 11.61
            width, height = 0.79 * size, 1.80 * size
            group.box(x - width, x + width, y, y + 2.25 * size, z - 0.60, z + height, "brick")
            sash(group, x, y - 0.16, z + 0.12, 0.94 * size, 1.43 * size)
            group.loft([
                [(x - width - 0.15, y - 0.30, z + height), (x + width + 0.15, y - 0.30, z + height),
                 (x + width + 0.15, y + 2.6 * size, z + height), (x - width - 0.15, y + 2.6 * size, z + height)],
                [(x - 0.025, y + (0.05 if index % 2 else 0.24), z + height + size),
                 (x + 0.025, y + (0.05 if index % 2 else 0.24), z + height + size),
                 (x + 0.025, y + 1.9 * size, z + height + size), (x - 0.025, y + 1.9 * size, z + height + size)],
            ], "clay")


def clock_tower(group):
    x, y = 2.99, 3.84
    for z0, z1, radius, surface in ((-0.45, 4.2, 3.86, "stone"), (4.2, 18.02, 3.83, "brick"),
                                     (18.02, 23.82, 3.67, "brick")):
        group.box(x - radius, x + radius, y - radius, y + radius, z0, z1, surface)
    for z, height, radius in ((4.22, 0.22, 4.0), (9.57, 0.24, 4.0), (12.73, 0.30, 4.04),
                              (17.87, 0.22, 3.99), (18.12, 0.30, 4.07), (23.43, 0.23, 4.0), (23.80, 0.35, 4.16)):
        group.box(x - radius, x + radius, y - radius, y + radius, z, z + height, "highlight")
    for side in range(4):
        start = len(group.vertices)
        front = -3.74
        for offset in (-2.96, -2.42, 2.42, 2.96):
            column(group, offset, front - 0.09, 18.53, 23.45, 0.245)
        for offset in (-3.56, 3.56):
            for index in range(22):
                z = 4.48 + index * 0.59
                group.box(offset - 0.14, offset + 0.14, -4.0, -3.72, z, z + 0.35, "trim")
        for z, width, height in ((1.10, 1.60, 2.55), (5.18, 1.68, 3.10), (10.24, 1.39, 1.74), (13.79, 0.96, 2.58)):
            sash(group, 0, -4.16, z, width, height)
        center = 20.91
        group.rod((0, front, center), (0, front - 0.18, center), 1.64, "trim", 48)
        group.rod((0, front - 0.18, center), (0, front - 0.25, center), 1.43, "metal", 48)
        group.rod((0, front - 0.25, center), (0, front - 0.30, center), 1.34, "clock", 48)
        for tick in range(60):
            angle = tick * tau / 60
            inner = 1.11 if tick % 5 == 0 else 1.21
            group.rod((inner * sin(angle), front - 0.32, center + inner * cos(angle)),
                      (1.27 * sin(angle), front - 0.32, center + 1.27 * cos(angle)),
                      0.024 if tick % 5 == 0 else 0.011, "metal", 5)
        for angle, length, radius in ((-pi / 3, 0.80, 0.055), (pi / 3, 1.10, 0.039)):
            group.rod((0, front - 0.36, center),
                      (length * sin(angle), front - 0.36, center + length * cos(angle)), radius, "metal", 9, 0.015)
        group.rod((0, front - 0.30, center), (0, front - 0.424, center), 0.089, "bronze", 12)
        group.transform(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(side * pi / 2, 4, "Z"), start)

    profile = ((24.12, 3.82), (24.66, 3.58), (25.31, 3.01), (26.02, 2.60), (26.77, 2.49),
               (27.55, 2.26), (28.25, 1.79), (28.84, 1.11), (29.20, 0.53), (29.4, 0.35))
    square = ((-1, -0.82), (-0.82, -1), (0.82, -1), (1, -0.82), (1, 0.82), (0.82, 1), (-0.82, 1), (-1, 0.82))
    rings = [[(x + radius * u, y + radius * v, z) for u, v in square] for z, radius in profile]
    group.loft(rings, "dome")
    for index in range(len(square)):
        for lower, upper in zip(rings[:-1], rings[1:], strict=True):
            group.rod(lower[index], upper[index], 0.040, "bronze", 5)
    for z0, z1, r0, r1 in ((29.40, 29.65, 0.41, 0.35), (29.65, 30.15, 0.31, 0.20),
                           (30.15, 30.32, 0.26, 0.23), (30.32, 31.10, 0.14, 0.014)):
        group.rod((x, y, z0), (x, y, z1), r0, "bronze", 12, r1)


def forecourt(group):
    group.box(-5.3, 33.0, -6.12, 0.9, -0.38, 0.22, "pavers")
    stairs = (11.2, 19.8)
    for left, right in ((-5.3, stairs[0]), (stairs[1], 33.0)):
        group.box(left, right, -6.42, -5.96, -2.96, 0.34, "stone")
        group.box(left - 0.08, right + 0.08, -6.55, -5.88, 0.34, 0.47, "highlight")
        for x in (left + 0.32, right - 0.32):
            group.box(x - 0.30, x + 0.30, -6.47, -5.90, -2.96, 0.78, "stone")
            group.box(x - 0.35, x + 0.35, -6.52, -5.85, 0.78, 0.90, "highlight")
    for index in range(15):
        y = -10.36 + 0.283 * index
        top = -2.58 + 0.200 * index
        group.box(*stairs, y, y + 0.288, -2.96, top, "pavement")
        group.box(stairs[0] - 0.015, stairs[1] + 0.015, y - 0.022, y + 0.042,
                  top - 0.048, top + 0.007, "highlight")
    for x in (11.53, 19.47):
        group.rod((x, -10.15, -1.78), (x, -6.20, 1.14), 0.042, "metal")
        for index in range(5):
            group.rod((x, -10.08 + index * 0.90, -2.41 + index * 0.64),
                      (x, -10.08 + index * 0.90, -1.73 + index * 0.66), 0.027, "metal")
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
    for left, right in ((-4.7, 9.8), (21.1, 32.4)):
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


def replace_headhouse(scene, legacy):
    archived_frame = station_frame(legacy)
    frame_to_legacy = archived_frame.inverted() @ legacy.matrix_world
    # Blender object transforms serialize location, rotation and scale. Publish
    # that same representable placement instead of the unsaved affine shear.
    frame = Matrix.LocRotScale(*archived_frame.decompose())
    old = legacy.data
    # The locked archive merges both buildings. Shed cladding and structure start
    # beyond the rear third of the headhouse, including their overlapping ends.
    shed_surfaces = {"RVA_Stone_756C5F", "RVA_Glass_385054", "RVA_Slate_4E5658",
                     "RVA_Metal_676F70", "RVA_Paint_607879", "RVA_Paint_789294"}
    shed = bmesh.new()
    shed.from_mesh(old)
    keep = {face for face in shed.faces if old.materials[face.material_index].name in shed_surfaces
            and all((frame_to_legacy @ v.co).y > 20 for v in face.verts)}
    if not 100 < len(keep) < len(shed.faces) or not any(
            (frame_to_legacy @ v.co).y > 170 for face in keep for v in face.verts):
        shed.free()
        raise ValueError("The archived station no longer matches the headhouse / train-shed split.")
    bmesh.ops.delete(shed, geom=[face for face in shed.faces if face not in keep], context="FACES_ONLY")
    bmesh.ops.delete(shed, geom=[vertex for vertex in shed.verts if not vertex.link_faces], context="VERTS")
    shed.to_mesh(old)
    shed.free()
    legacy.name = "Main Street Station — archived train shed"

    collection = bpy.data.collections.new("Main Street Station | street detail")
    scene.collection.children.link(collection)
    materials = station_materials()
    objects = []
    for name, builder in (("Headhouse", headhouse), ("Red clay hip and dormers", tiled_roof),
                          ("Clock tower", clock_tower), ("Main Street forecourt", forecourt)):
        group = MeshGroup(materials)
        builder(group)
        objects.append(group.object("MSS " + name, collection, frame))
    objects.append(scene_sign(collection, frame, materials["cream"]))
    return frame, objects
