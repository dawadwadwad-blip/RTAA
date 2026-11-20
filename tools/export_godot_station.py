"""Export a street-scale Godot scene from the assembled station Blender file."""

import json
from math import cos, sin, tau
from pathlib import Path
from random import Random
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "godot" / "station_trial" / "assets"
BOUNDS = (-808, 225, -613, 421)
GROUND = {"Terrain", "Roads_and_paths"}
EAST_LOT = (51.0, 3.0, 85.0, 83.0)


def inside(points):
    west, south, east, north = BOUNDS
    return (max(p.x for p in points) >= west and min(p.x for p in points) <= east
            and max(p.y for p in points) >= south and min(p.y for p in points) <= north)


def crop_ground(obj, include=inside, exclude=None):
    mesh = obj.data
    points = [obj.matrix_world @ v.co for v in mesh.vertices]
    remap, vertices, faces, materials = {}, [], [], []
    for face in mesh.polygons:
        indices = list(face.vertices)
        face_points = [points[i] for i in indices]
        if not include(face_points) or (exclude is not None and exclude(face_points)):
            continue
        for i in indices:
            if i not in remap:
                remap[i] = len(vertices)
                vertices.append(mesh.vertices[i].co)
        faces.append([remap[i] for i in indices])
        materials.append(face.material_index)
    cropped = bpy.data.meshes.new(obj.name + " trial")
    cropped.from_pydata(vertices, [], faces)
    for material in mesh.materials:
        cropped.materials.append(material)
    for face, index in zip(cropped.polygons, materials):
        face.material_index = index
    obj.data = cropped


def clip_face(points, bounds):
    """Clip a terrain face in local XY and interpolate Z on the source face."""
    left, near, right, far = bounds
    for axis, cut, direction in ((0, left, 1), (0, right, -1), (1, near, 1), (1, far, -1)):
        if not points:
            return points
        clipped = []
        a = points[-1]
        for b in points:
            inside_a = direction * (a[axis] - cut) >= 0
            inside_b = direction * (b[axis] - cut) >= 0
            if inside_a != inside_b:
                clipped.append(a.lerp(b, (cut - a[axis]) / (b[axis] - a[axis])))
            if inside_b:
                clipped.append(b)
            a = b
        points = clipped
    return points


def east_forecourt(frame):
    """Dress the parking-side view with simple original geometry over the pilot terrain."""
    sys.path.insert(0, str(ROOT / "tools"))
    from station_headhouse import MeshGroup
    from station_surfaces import material

    terrain = bpy.context.scene.objects["Terrain"]
    terrain_inverse = terrain.matrix_world.inverted()
    world_to_station = frame.inverted()
    surface = BVHTree.FromObject(terrain, bpy.context.evaluated_depsgraph_get())

    def ground(x, y):
        start = terrain_inverse @ (frame @ Vector((x, y, 50)))
        down = terrain_inverse.to_3x3() @ Vector((0, 0, -1))
        hit = surface.ray_cast(start, down, 75)[0]
        if hit is None:
            raise ValueError(f"East forecourt point {x:g}, {y:g} is beyond the terrain.")
        return (world_to_station @ (terrain.matrix_world @ hit)).z

    rock = bpy.data.materials["MSS Rusticated foundation stone"]
    group = MeshGroup({"asphalt": material("MSS East lot asphalt", (0.125, 0.125, 0.115)),
                       "stripe": material("MSS East lot markings", (0.68, 0.65, 0.54)),
                       "rock": rock, "bark": material("MSS Tree bark", (0.088, 0.053, 0.028)),
                       "leaf": material("MSS Tree leaf", (0.075, 0.137, 0.038)),
                       "leaf_light": material("MSS Tree leaf light", (0.13, 0.197, 0.062))})

    terrain_to_station = world_to_station @ terrain.matrix_world
    points = [terrain_to_station @ vertex.co for vertex in terrain.data.vertices]

    def veneer(polygon, lift, finish):
        if len(polygon) < 3:
            return
        raised = [(point.x, point.y, point.z + lift) for point in polygon]
        group.shape(raised, [(0, i, i + 1) for i in range(1, len(raised) - 1)], finish)

    for face in terrain.data.polygons:
        polygon = [points[i] for i in face.vertices]
        if (max(p.x for p in polygon) < EAST_LOT[0] or min(p.x for p in polygon) > EAST_LOT[2]
                or max(p.y for p in polygon) < EAST_LOT[1] or min(p.y for p in polygon) > EAST_LOT[3]):
            continue
        veneer(clip_face(polygon, EAST_LOT), 0.205, "asphalt")
        if min(p.x for p in polygon) <= 55.8:
            for y in range(13, 68, 3):
                if min(p.y for p in polygon) <= y + 0.10 and max(p.y for p in polygon) >= y:
                    veneer(clip_face(polygon, (51.8, y, 55.8, y + 0.10)), 0.221, "stripe")
    for y in range(9, 60, 3):
        bottom = ground(49, y + 1.5)
        group.box(48.65, 49.25, y, y + 3.03, bottom - 0.40, bottom + 0.87, "rock")
    rng = Random(19)
    for x, y, height in ((40, 3, 6.4), (43, 11, 7.6), (45, 19, 6.1), (43, 28, 7.4), (43, 41, 6.3),
                         (44, 53, 6.0), (44, 69, 5.5)):
        tree(group, rng, x, y, ground(x, y), height)
    group.object("MSS East forecourt setting", bpy.context.scene.collection, frame)


def tree(group, rng, x, y, base, height, clusters=8):
    group.rod((x, y, base - 0.18), (x + 0.21, y, base + height * 0.78), 0.22, "bark", 7, 0.081)
    for i in range(clusters):
        angle = tau * i / clusters
        cx = x + cos(angle) * rng.uniform(0.45, 1.75)
        cy = y + sin(angle) * rng.uniform(0.45, 1.75)
        z = base + height * rng.uniform(0.61, 0.91)
        radius = rng.uniform(1.18, 1.86)
        profiles = []
        for dz, width in ((-1.19, 0.12), (-0.67, 0.79), (0.26, 1.0), (0.96, 0.62), (1.37, 0.08)):
            profiles.append([(cx + radius * width * cos(tau * t / 9) * rng.uniform(0.84, 1.18),
                              cy + radius * width * sin(tau * t / 9) * rng.uniform(0.84, 1.18),
                              z + dz + rng.uniform(-0.14, 0.14)) for t in range(9)])
        group.loft(profiles, "leaf_light" if i % 3 == 0 else "leaf")


def export():
    report = json.loads((ROOT / "reports/station_approach.json").read_text())
    crosswalk = next(row for row in report["witnesses"] if row["name"] == "station_crosswalk")
    east, north = crosswalk["local_en_m"]
    origin = Vector((east, north, 0))
    road_axis = report["station_frame"]
    frame = Matrix(road_axis)
    tangent = Vector((road_axis[0][0], -road_axis[1][0])).normalized()
    ASSETS.mkdir(parents=True, exist_ok=True)
    east_forecourt(frame)

    sys.path.insert(0, str(ROOT / "tools"))
    from godot_corridor_dressing import Corridor

    corridor = Corridor.from_legacy(ROOT / "outputs/east-main-corridor")
    bpy.ops.object.select_all(action="DESELECT")
    selected = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        bounds = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
        if not (obj.name.startswith("Corridor_") or inside(bounds) or corridor.includes(bounds)):
            continue
        if obj.name in GROUND:
            crop_ground(obj, lambda p: inside(p) or corridor.includes(p, terrain=True),
                        corridor.overlaps_legacy_road if obj.name == "Roads_and_paths" else None)
        selected.append(obj)
    selected.extend(corridor.dress(selected, tree))
    for obj in selected:
        transform = obj.matrix_world.copy()
        transform.translation -= origin
        obj.matrix_world = transform
        obj.select_set(True)
    if len(selected) < 12 or "FINISHED" not in bpy.ops.export_scene.gltf(
            filepath=str(ASSETS / "shockoe.glb"), export_format="GLB", use_selection=True,
            export_tangents=True, export_image_format="AUTO"):
        raise RuntimeError("Unable to export the complete station trial scene.")
    def godot_point(point):
        x, y, z = frame @ Vector(point) - origin
        return [x, z, -y]

    views = [
        {"name": name, "eye": godot_point(eye), "target": godot_point(target), "fov": fov}
        for name, eye, target, fov in (
            ("Southwest facade", (7, -23.1, -0.86), (14, 0, 11.8), 68.0),
            ("Southeast platform", (80.5, 10, -0.77), (11, 45, 10.1), 64.0),
        )
    ]
    route = {"origin_en": [east, north], "eastbound_xz": list(tangent), "station_views": views,
             "ground_meshes": ["Terrain", "Roads_and_paths", "East_Main_Approach_Road", "Corridor_Terrain", "Corridor_Road"],
             "attribution": report["attribution"]}
    route.update(corridor.gameplay())
    (ASSETS / "route.json").write_text(json.dumps(route, indent=2) + "\n")
    print(f"PASS: Exported {len(selected)} Shockoe meshes in meters around the station crossing.")


if __name__ == "__main__":
    export()
