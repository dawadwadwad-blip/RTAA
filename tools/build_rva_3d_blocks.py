"""Build terrain-fit Richmond GLB chunks using an installed Blender in background mode."""

import argparse
from collections import Counter, defaultdict
from itertools import product
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile


MATERIALS = {
    "M_Facade_Brick": ((0.36, 0.17, 0.11, 1.0), 0.92, 0.0),
    "M_Facade_Pod_Modern": ((0.33, 0.42, 0.46, 1.0), 0.52, 0.16),
    "M_Roof_Slate": ((0.12, 0.14, 0.17, 1.0), 0.86, 0.0),
    "M_Parody_Billboard": ((0.24, 0.19, 0.13, 1.0), 0.80, 0.0),
}
DISTRICTS = {
    "belle_isle": (-77.4501, 37.5276),
    "carver_jackson_ward": (-77.4466, 37.5519),
    "church_hill": (-77.4180, 37.5320),
    "downtown": (-77.4397, 37.5410),
    "manchester": (-77.4470, 37.5175),
    "museum_district": (-77.4825, 37.5567),
    "northside": (-77.4349, 37.5681),
    "oregon_hill": (-77.4536, 37.5406),
    "scotts_addition": (-77.4735, 37.5695),
    "shockoe_bottom": (-77.4267, 37.5315),
    "shockoe_slip": (-77.4349, 37.5352),
    "the_fan": (-77.4658, 37.5508),
    "union_hill": (-77.4169, 37.5430),
}
CHUNK_SCHEMA = "rva-gis-chunks/1"
STATION_OSM_ID = "osm/way/113030476"
STATION_ASSET = "authored/rva_main_street_station.glb"
STATION_MESHES = {
    "MSS Headhouse", "MSS Red clay hip and dormers", "MSS Clock tower",
    "MSS Main Street forecourt", "MSS Restored train shed", "Main Street Station lettering",
}
FOUNDATION_BURY_M = 0.06
MAX_FOUNDATION_SIMPLIFICATION_M = 0.015
NUMBER = r"\d+(?:\.\d+)?"


def height_tag(value):
    text = value.strip().lower().replace(",", ".").replace("′", "'").replace("″", '"')
    metric = re.fullmatch(fr"({NUMBER})\s*(m|meter|meters|metre|metres|ft|foot|feet)?", text)
    imperial = re.fullmatch(fr"""({NUMBER})\s*'\s*(?:({NUMBER})\s*")?""", text)
    if metric:
        height = float(metric[1]) * (0.3048 if metric[2] in {"ft", "foot", "feet"} else 1.0)
    elif imperial and float(imperial[2] or 0) < 12:
        height = float(imperial[1]) * 0.3048 + float(imperial[2] or 0) * 0.0254
    else:
        return None
    return height if 0.5 <= height <= 350 else None


def building_height(tags, district, area):
    direct = height_tag(tags.get("height", ""))
    if direct is not None:
        return direct, "osm_height"
    use = tags.get("building", "").lower()
    levels = tags.get("building:levels", "").strip()
    if re.fullmatch(NUMBER, levels) and 1 <= float(levels) <= 90:
        floor = 3.5 if use in {"office", "commercial", "retail", "industrial"} else 3.1
        return float(levels) * floor + (height_tag(tags.get("roof:height", "")) or 0.5), "osm_levels"
    if use in {"shed", "garage", "garages", "carport", "hut", "roof"}:
        height = 3.0
    elif use in {"warehouse", "industrial", "factory", "hangar"}:
        height = 7.0 if area < 2000 else 9.0
    elif use in {"office", "commercial", "hotel", "apartments", "retail"} and district == "downtown":
        height = 14.0 if area < 450 else 24.0
    elif use in {"apartments", "hotel", "office", "commercial"}:
        height = 10.0 if area < 650 else 14.0
    elif use in {"house", "detached", "semidetached_house", "terrace", "residential"}:
        height = 9.3 if area >= 105 and district in {"the_fan", "church_hill", "union_hill"} else 6.8
    elif use == "church":
        height = 12.0
    elif district == "downtown" and area >= 650:
        height = 17.0
    else:
        height = 6.8 if area >= 42 else 3.4
    return height, "district_default"


def facade(tags):
    fabric = tags.get("building:material", "").lower()
    if fabric in {"glass", "metal", "steel", "concrete", "aluminium", "plastic", "cladding"}:
        return "M_Facade_Pod_Modern"
    style = tags.get("building:architecture", "").lower()
    if not fabric and (style in {"modern", "modernist", "contemporary", "brutalist"}
                       or tags.get("parking") == "multi-storey" or tags.get("building") == "parking"):
        return "M_Facade_Pod_Modern"
    return "M_Facade_Brick"


class Terrain:
    def __init__(self, grid, codes, np):
        self.np = np
        self.west, _, _, self.north = grid["bounds_en_m"]
        self.dx, self.dy = grid["pixel_size_en_m"]
        self.height, self.width = codes.shape
        self.z = codes.astype(np.float64) * grid["z_scale_per_code_m"] + grid["z_offset_m"]

    def pixels(self, east, north):
        return (east - self.west) / self.dx - 0.5, (self.north - north) / self.dy - 0.5

    def sample(self, x, y):
        if not (-1e-6 <= x <= self.width - 1 + 1e-6 and -1e-6 <= y <= self.height - 1 + 1e-6):
            raise ValueError("complete footprint is outside the heightmap sample grid")
        x = min(max(x, 0), self.width - 1)
        y = min(max(y, 0), self.height - 1)
        ix, iy = min(int(x), self.width - 2), min(int(y), self.height - 2)
        u, v = x - ix, y - iy
        nw = self.z[iy, ix]
        se = self.z[iy + 1, ix + 1]
        if u >= v:
            return float(nw + (self.z[iy, ix + 1] - nw) * u + (se - self.z[iy, ix + 1]) * v)
        return float(nw + (se - self.z[iy + 1, ix]) * u + (self.z[iy + 1, ix] - nw) * v)

    def edge(self, a, b):
        """Sample the exact intersections with the heightfield's triangle edges."""
        ax, ay = self.pixels(*a)
        bx, by = self.pixels(*b)
        stops = {0.0, 1.0}
        for start, end in ((ax, bx), (ay, by), (ax - ay, bx - by)):
            delta = end - start
            if abs(delta) > 1e-9:
                for k in range(math.floor(min(start, end)) + 1, math.ceil(max(start, end))):
                    u = (k - start) / delta
                    if 1e-8 < u < 1 - 1e-8:
                        stops.add(round(u, 10))
        return [(u, self.sample(ax + u * (bx - ax), ay + u * (by - ay))) for u in sorted(stops)]

    def interior_peak(self, polygon, intersects_xy):
        w, s, e, n = polygon.bounds
        x0, y0 = self.pixels(w, n)
        x1, y1 = self.pixels(e, s)
        cols = self.np.arange(math.ceil(x0), math.floor(x1) + 1)
        rows = self.np.arange(math.ceil(y0), math.floor(y1) + 1)
        if not (cols.size and rows.size):
            return -math.inf
        xx = self.west + (cols[None, :] + 0.5) * self.dx
        yy = self.north - (rows[:, None] + 0.5) * self.dy
        inside = intersects_xy(polygon, xx, yy)
        samples = self.z[self.np.ix_(rows, cols)][inside]
        return float(samples.max()) if samples.size else -math.inf


def simplify_profile(samples):
    kept = [samples[0]]
    anchor = 0
    for end in range(2, len(samples)):
        u0, z0 = samples[anchor]
        u1, z1 = samples[end]
        slope = (z1 - z0) / (u1 - u0)
        if any(abs(z - (z0 + (u - u0) * slope)) > MAX_FOUNDATION_SIMPLIFICATION_M
               for u, z in samples[anchor + 1:end]):
            kept.append(samples[end - 1])
            anchor = end - 1
    kept.append(samples[-1])
    return kept


class Mesh:
    def __init__(self, origin):
        self.origin = origin
        self.vertices = []
        self.faces = []
        self.surface_names = []
        self.texcoords = []
        self.indices = {}

    def add(self, points, name, uv):
        indices = []
        for east, north, z in points:
            point = (round(east - self.origin[0], 6), round(north - self.origin[1], 6),
                     round(z - self.origin[2], 6))
            index = self.indices.get(point)
            if index is None:
                index = len(self.vertices)
                self.indices[point] = index
                self.vertices.append(point)
            indices.append(index)
        if len(set(indices)) == len(indices):
            self.faces.append(indices)
            self.surface_names.append(name)
            self.texcoords.append(uv)

    def data(self):
        return {"vertices": self.vertices, "faces": self.faces,
                "materials": self.surface_names, "uv": self.texcoords}


def walls(mesh, profiles, roof_elevation, reference, material):
    for ring in profiles:
        distance = 0.0
        for a, b, samples in ring:
            dx, dy = b[0] - a[0], b[1] - a[1]
            span = math.hypot(dx, dy)
            if span < 1e-5:
                continue
            samples = simplify_profile(samples)
            for (u0, z0), (u1, z1) in zip(samples, samples[1:]):
                x0, y0 = a[0] + dx * u0, a[1] + dy * u0
                x1, y1 = a[0] + dx * u1, a[1] + dy * u1
                if math.hypot(x1 - x0, y1 - y0) < 1e-5:
                    continue
                low0, low1 = z0 - FOUNDATION_BURY_M, z1 - FOUNDATION_BURY_M
                tu0, tu1 = (distance + span * u0) / 3.0, (distance + span * u1) / 3.0
                v = (roof_elevation - reference) / 3.0
                mesh.add([(x0, y0, low0), (x1, y1, low1), (x1, y1, roof_elevation),
                          (x0, y0, roof_elevation)], material,
                         [(tu0, (low0 - reference) / 3.0), (tu1, (low1 - reference) / 3.0),
                          (tu1, v), (tu0, v)])
            distance += span


def add_billboard(mesh, edges, tags, base, height):
    use = tags.get("building", "").lower()
    if height < 6 or (use not in {"retail", "commercial", "office", "hotel"} and not tags.get("shop")):
        return False
    # Keep signage on the valid straight facade with the most room.
    a, b, _ = max(edges, key=lambda edge: math.dist(edge[0], edge[1]))
    length = math.dist(a, b)
    if length < 5:
        return False
    tx, ty = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    width = min(4.5, length * 0.52)
    x, y = (a[0] + b[0]) / 2 + ty * 0.025, (a[1] + b[1]) / 2 - tx * 0.025
    x0, y0 = x - tx * width / 2, y - ty * width / 2
    x1, y1 = x + tx * width / 2, y + ty * width / 2
    z = base + min(max(3.0, height * 0.46), height - 1.7)
    mesh.add([(x0, y0, z), (x1, y1, z), (x1, y1, z + 0.85), (x0, y0, z + 0.85)],
             "M_Parody_Billboard", [(0, 0), (1, 0), (1, 1), (0, 1)])
    return True


def export_with_bpy(plan_path, export_dir):
    """This entry point runs in Blender's bundled Python with only bpy and stdlib."""
    import bpy

    if bpy.app.version < (4, 2, 0):
        raise RuntimeError("Use Blender 4.2 LTS or later.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = {}
    for name, (color, roughness, metallic) in MATERIALS.items():
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        material.diffuse_color = color
        materials[name] = material
    for entry in plan["chunks"]:
        data = json.loads((plan_path.parent / entry["plan_file"]).read_text(encoding="utf-8"))
        nodes = []
        for key, suffix in (("shell", "-col"), ("signs", "_signs")):
            item = data[key]
            if not item["faces"]:
                continue
            name = entry["id"] + suffix
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(item["vertices"], [], item["faces"])
            if mesh.validate(verbose=False):
                raise ValueError(f"Blender repaired invalid geometry in {name}; export halted")
            mesh.update()
            present = set(item["materials"])
            used = [name for name in MATERIALS if name in present]
            for surface in used:
                mesh.materials.append(materials[surface])
            slots = {surface: index for index, surface in enumerate(used)}
            uv = mesh.uv_layers.new(name="UVMap")
            for poly, material, uvs in zip(mesh.polygons, item["materials"], item["uv"], strict=True):
                poly.material_index = slots[material]
                for loop, point in zip(poly.loop_indices, uvs, strict=True):
                    uv.data[loop].uv = point
            node = bpy.data.objects.new(name, mesh)
            bpy.context.scene.collection.objects.link(node)
            node.select_set(True)
            nodes.append(node)
        target = export_dir / entry["glb"]
        bpy.context.view_layer.objects.active = nodes[0]
        result = bpy.ops.export_scene.gltf(
            filepath=str(target), export_format="GLB", use_selection=True, export_yup=True,
            export_animations=False, export_cameras=False, export_lights=False,
            export_texcoords=True, export_normals=True,
        )
        if result != {"FINISHED"} or not target.is_file():
            raise RuntimeError(f"Blender failed to export {target}")
        for node in nodes:
            mesh = node.data
            bpy.data.objects.remove(node, do_unlink=True)
            bpy.data.meshes.remove(mesh)


def read_glb(path):
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) != 20:
            raise ValueError(f"Truncated GLB {path}")
        magic, version, length, json_length, kind = struct.unpack("<4sIII4s", header)
        if (magic, version, length, kind) != (b"glTF", 2, size, b"JSON") or not 0 < json_length <= size - 20:
            raise ValueError(f"Invalid GLB header in {path}")
        return json.loads(handle.read(json_length))


def glb_info(path, chunk):
    data = read_glb(path)
    if not any(node.get("name") == chunk["id"] + "-col" and "mesh" in node for node in data["nodes"]):
        raise ValueError(f"No Godot collision node in {path}")
    material_names = [item.get("name") for item in data.get("materials", [])]
    if set(material_names) != set(chunk["materials"]):
        raise ValueError(f"Lost named material slots in {path}")
    triangles = 0
    for mesh in data["meshes"]:
        for primitive in mesh["primitives"]:
            if not {"POSITION", "NORMAL", "TEXCOORD_0"} <= primitive["attributes"].keys():
                raise ValueError(f"Missing position, normal or UV attribute in {path}")
            if primitive.get("mode", 4) != 4 or "indices" not in primitive:
                raise ValueError(f"Expected indexed triangles in {path}")
            triangles += data["accessors"][primitive["indices"]]["count"] // 3
    return triangles


def station_landmark(source, snapshot, features, terrain, project, np):
    from fetch_rva_gis import ORIGIN_EN, load_json, sha256
    from shapely.geometry import box, shape
    from shapely.ops import transform

    matching = [item for item in features if item.get("id") == STATION_OSM_ID]
    if len(matching) != 1 or matching[0]["properties"]["tags"].get("wikidata") != "Q141093771":
        raise ValueError("This GIS snapshot does not contain the mapped Main Street Station footprint.")
    sidecar = load_json(source.with_suffix(".json"))
    if sidecar.get("asset") != source.name or sidecar.get("objects") != len(STATION_MESHES):
        raise ValueError("Use the authored station exterior GLB and its matching JSON sidecar.")
    frame = np.asarray(sidecar["headhouse_xyz_m_to_pilot_east_north_up_m"], dtype=float)
    if (frame.shape != (4, 4) or not np.isfinite(frame).all()
            or not np.allclose(frame[3], [0, 0, 0, 1])
            or not np.allclose(frame[:3, 2], [0, 0, 1], atol=0.0001)
            or not np.allclose(frame[2, :2], [0, 0], atol=0.0001)
            or not np.allclose(frame[:3, :3].T @ frame[:3, :3], np.eye(3), atol=0.01)
            or not 0.99 < np.linalg.det(frame[:3, :3]) < 1.01):
        raise ValueError("Unexpected Main Street Station placement matrix.")
    gltf = read_glb(source)
    nodes = gltf["nodes"]
    if ({node.get("name") for node in nodes} != STATION_MESHES or len(nodes) != len(STATION_MESHES)
            or any("mesh" not in node or {"matrix", "translation", "rotation", "scale", "children"} & node.keys()
                   for node in nodes)
            or any("uri" in item for item in [*gltf.get("buffers", []), *gltf.get("images", [])])):
        raise ValueError("Expected six baked station meshes with self-contained textures.")
    # The station source stores Blender (frontage, toward shed, up); glTF stores
    # (frontage, up, toward street). The destination uses (east, up, south).
    axis_change = np.asarray([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)
    basis = axis_change @ frame[:3, :3] @ axis_change.T
    dx, dn = np.asarray(ORIGIN_EN) - np.asarray(snapshot["origin_grid_m_en"])
    world_zero = float(snapshot["origin_elevation_m"])
    origin = axis_change @ frame[:3, 3] + [dx, -world_zero, -dn]
    east, north = snapshot["origin_grid_m_en"]
    contacts = []
    for x in (6.15, 13.77, 21.17, 25.29):
        point = basis @ [x, -2.58, 10.36] + origin
        grade = terrain.sample(*terrain.pixels(east + point[0], north - point[2])) - world_zero
        contacts.append((point, grade))
    fit = float(np.median([grade + 0.16 - point[1] for point, grade in contacts]))
    if abs(fit) > 0.35 or any(not 0.04 <= point[1] + fit - grade <= 0.28 for point, grade in contacts):
        raise ValueError("Station stair contact differs too much from the GIS terrain; review the local grade.")
    origin[1] += fit
    bounds = []
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            position = gltf["accessors"][primitive["attributes"]["POSITION"]]
            bounds.extend(basis @ corner + origin for corner in product(*zip(position["min"], position["max"])))
    limits = np.asarray(bounds)
    low, high = limits.min(axis=0), limits.max(axis=0)
    footprint = transform(project.transform, shape(matching[0]["geometry"]))
    envelope = box(east + low[0], north - high[2], east + high[0], north - low[2])
    covered = footprint.intersection(envelope).area / footprint.area if footprint.area > 0 else 0.0
    if covered < 0.9:
        raise ValueError("The authored station is misaligned with its mapped footprint.")
    return {
        "id": "main_street_station", "glb": STATION_ASSET, "sha256": sha256(source),
        "replaces_osm_id": STATION_OSM_ID, "neighborhood": "shockoe_bottom",
        "basis_godot_columns": basis.T.tolist(), "origin_godot_m": origin.tolist(),
        "world_bounds_godot_m": [low.tolist(), high.tolist()],
        "osm_footprint_coverage_in_model_envelope": covered,
        "terrain_adjustment_m": fit,
        "first_step_heights_above_ground_m": [float(point[1] + fit - grade) for point, grade in contacts],
    }


def footprint_profile(polygon, terrain, intersects_xy):
    profiles = []
    for ring in [polygon.exterior, *polygon.interiors]:
        points = list(ring.coords)
        profiles.append([(a, b, terrain.edge(a, b)) for a, b in zip(points, points[1:]) if a != b])
    perimeter = max(z for ring in profiles for _, _, nodes in ring for _, z in nodes)
    return max(perimeter, terrain.interior_peak(polygon, intersects_xy)), profiles


def chunk_id(neighborhood, cx, cy):
    return f"rva_{neighborhood}_e{cx:+04d}_n{cy:+04d}".replace("+", "p").replace("-", "m")


def prepare(data_dir, plan_dir, cell_size, station=None):
    import numpy as np
    from PIL import Image
    from pyproj import Transformer
    from shapely import constrained_delaunay_triangles, intersects_xy, orient_polygons
    from shapely.geometry import shape
    from shapely.errors import GEOSException
    from shapely.ops import transform

    from fetch_rva_gis import EPSG, PROJECTION, SCHEMA, load_json, parts_of, sha256, write_json

    manifest_path = data_dir / "rva_gis_manifest.json"
    src = load_json(manifest_path)
    if src["schema"] != SCHEMA or src["horizontal_epsg"] != EPSG or src["source_projection"] != PROJECTION:
        raise ValueError("Run the matching fetch_rva_gis.py before building these meshes.")
    grid = src["heightmap"]
    if grid["sample_position"] != "pixel_center" or grid["surface_model"] != "linear_triangles_nw_se":
        raise ValueError("Unrecognized terrain sample layout.")
    for name in ("rva_buildings.geojson", "rva_heightmap.png"):
        if sha256(data_dir / name) != src["files_sha256"].get(name):
            raise ValueError(f"{name} does not match the GIS snapshot's checksum.")
    with Image.open(data_dir / "rva_heightmap.png") as image:
        columns, rows = grid["size_px"]
        codes = np.asarray(image)
        if (image.format != "PNG" or image.mode not in {"I;16", "I;16B", "I;16L", "I"}
                or codes.shape != (rows, columns) or min(rows, columns) < 2
                or codes.min() < 0 or codes.max() > 65535):
            raise ValueError("Unexpected format or dimensions for the 16-bit terrain PNG.")
        terrain = Terrain(grid, codes, np)
    origin_e, origin_n = src["origin_grid_m_en"]
    origin_z = src["origin_elevation_m"]
    project = Transformer.from_pipeline(PROJECTION)
    centers = {name: project.transform(*lonlat, errcheck=True) for name, lonlat in DISTRICTS.items()}
    data = load_json(data_dir / "rva_buildings.geojson")
    landmark = station_landmark(station, src, data["features"], terrain, project, np) if station else None
    groups = defaultdict(list)
    rejected = []
    for item in data["features"]:
        if landmark and item["id"] == landmark["replaces_osm_id"]:
            continue
        try:
            geometry = shape(item["geometry"])
            projected = orient_polygons(transform(project.transform, geometry))
            if not projected.is_valid or projected.is_empty:
                raise ValueError("projection produced invalid footprint geometry")
            center = projected.representative_point()
            xy = center.x, center.y
            neighborhood = min(centers, key=lambda name: math.dist(xy, centers[name]))
            cx = math.floor((center.x - origin_e) / cell_size)
            cy = math.floor((center.y - origin_n) / cell_size)
            groups[(neighborhood, cx, cy)].append((item, projected))
        except (KeyError, ValueError, GEOSException) as exc:
            rejected.append({"id": item.get("id"), "reason": str(exc)})
    chunks = []
    totals = Counter()
    for (neighborhood, cx, cy), group in sorted(groups.items()):
        name = chunk_id(neighborhood, cx, cy)
        offset_e, offset_n = cx * cell_size, cy * cell_size
        origin = origin_e + offset_e, origin_n + offset_n, origin_z
        shell, signs = Mesh(origin), Mesh(origin)
        counts = Counter()
        for item, geometry in group:
            tags = item["properties"]["tags"]
            parts = list(parts_of(geometry, "Polygon"))
            height, source = building_height(tags, neighborhood, geometry.area)
            try:
                ready = []
                for polygon in parts:
                    triangles = list(parts_of(constrained_delaunay_triangles(polygon), "Polygon"))
                    if not triangles or not math.isclose(sum(t.area for t in triangles), polygon.area, rel_tol=1e-8):
                        raise ValueError("roof triangulation does not cover the footprint")
                    grade, profiles = footprint_profile(polygon, terrain, intersects_xy)
                    ready.append((grade, profiles, triangles))
            except (ValueError, GEOSException) as exc:
                rejected.append({"id": item["id"], "reason": str(exc)})
                continue
            for grade, profiles, triangles in ready:
                roof = grade + height
                walls(shell, profiles, roof, grade, facade(tags))
                for face in triangles:
                    points = list(orient_polygons(face).exterior.coords)[:-1]
                    shell.add([(e, n, roof) for e, n in points], "M_Roof_Slate",
                              [((e - origin[0]) / 4.0, (n - origin[1]) / 4.0) for e, n in points])
            grade, profiles, _ = ready[0]
            if add_billboard(signs, profiles[0], tags, grade, height):
                counts["signs"] += 1
            counts["buildings"] += 1
            counts[source] += 1
            if tags.get("roof:shape", "flat") != "flat":
                counts["nonflat_roof_tags_built_flat"] += 1
        if not shell.faces:
            continue
        vertices = np.asarray(shell.vertices)
        low, high = vertices.min(axis=0), vertices.max(axis=0)
        file = f"{name}.json"
        write_json(plan_dir / file, {"shell": shell.data(), "signs": signs.data()})
        chunks.append({
            "id": name, "plan_file": file, "glb": name + ".glb", "neighborhood": neighborhood,
            "cell_en": [cx, cy], "origin_godot_m": [offset_e, 0.0, -offset_n],
            "world_bounds_godot_m": [
                [float(low[0] + offset_e), float(low[2]), float(-high[1] - offset_n)],
                [float(high[0] + offset_e), float(high[2]), float(-low[1] - offset_n)],
            ],
            "materials": sorted(set(shell.surface_names) | set(signs.surface_names)), "counts": dict(counts),
        })
        totals.update(counts)
    if not chunks:
        raise ValueError("No usable building chunks were produced.")
    plan = plan_dir / "plan.json"
    write_json(plan, {"chunks": chunks})
    return plan, {
        "schema": CHUNK_SCHEMA, "source_manifest_sha256": sha256(manifest_path),
        "streaming_cell_m": cell_size, "origin_grid_m_en": [origin_e, origin_n],
        "origin_elevation_m": origin_z, "neighborhood_assignment": "nearest district anchor; approximate",
        "foundation_bury_m": FOUNDATION_BURY_M,
        "foundation_profile_max_error_m": MAX_FOUNDATION_SIMPLIFICATION_M,
        "roof_height_reference": "highest decoded terrain sample inside or along each footprint shell",
        "collision": "Godot -col static trimesh on shells; separate signage without collision",
        "attributions": src["attributions"], "counts": dict(totals), "rejected": rejected, "chunks": chunks,
        "landmarks": [landmark] if landmark else [],
        "replaced_osm_ids": [landmark["replaces_osm_id"]] if landmark else [],
    }


def preserve_import_settings(target, stage, manifest):
    from fetch_rva_gis import load_json, sha256

    previous_manifest = target / "rva_chunks.json"
    if not previous_manifest.is_file():
        return
    previous = load_json(previous_manifest)
    files = {row["glb"]: row["sha256"] for row in [*previous["chunks"], *previous.get("landmarks", [])]}
    names = {row["glb"] for row in manifest["chunks"]}
    for path in target.rglob("*"):
        relative = path.relative_to(target).as_posix()
        if relative == "rva_chunks.json":
            continue
        if relative == "authored" and STATION_ASSET in files and path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Unexpected file in generated mesh folder: {path}")
        if relative == "authored/.gdignore" and STATION_ASSET in files and path.stat().st_size == 0:
            continue
        if relative in files and sha256(path) == files[relative]:
            continue
        if path.name.endswith(".glb.import") and path.name.removesuffix(".import") in files:
            if path.name.removesuffix(".import") in names:
                shutil.copy2(path, stage / path.name)
            continue
        raise ValueError(f"Refusing to replace a mesh directory containing an edited or untracked file: {path}")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("outputs/rva_gis"))
    parser.add_argument("--project-dir", type=Path, default=Path("godot/station_trial"),
                        help="Directory containing the destination project.godot.")
    parser.add_argument("--blender", help="Blender executable path when Blender is outside PATH.")
    parser.add_argument("--chunk-meters", type=int, default=504)
    parser.add_argument("--station-exterior", type=Path,
                        help="Use the authored Main Street Station GLB and its adjacent placement JSON.")
    args = parser.parse_args()
    if not 126 <= args.chunk_meters <= 1008:
        parser.error("--chunk-meters must be between 126 and 1008.")
    return args


def run_build():
    from fetch_rva_gis import check_snapshot, output_lock, publish_snapshot, sha256, write_json

    args = cli()
    project = args.project_dir.resolve()
    if not (project / "project.godot").is_file():
        raise ValueError(f"No project.godot exists in {project}; set --project-dir.")
    blender = shutil.which(args.blender or "blender")
    if not blender:
        raise ValueError("Blender 4.2+ is required. Pass --blender with the full executable path.")
    data = args.data_dir.resolve()
    target = project / "assets" / "rva_gis" / "meshes"
    with output_lock(target):
        check_snapshot(target, "rva_chunks.json", CHUNK_SCHEMA)
        with tempfile.TemporaryDirectory(prefix=".rva-building-build-", dir=target.parent) as work:
            workspace = Path(work)
            stage = workspace / "meshes"
            plans = workspace / "plans"
            stage.mkdir()
            plans.mkdir()
            with output_lock(data):
                plan, manifest = prepare(data, plans, args.chunk_meters, args.station_exterior)
            print(f"Building {len(manifest['chunks'])} chunks with {manifest['counts']['buildings']} footprints.", flush=True)
            subprocess.run([
                blender, "--background", "--factory-startup", "--python-exit-code", "1",
                "--python", str(Path(__file__).resolve()), "--", "--export-plan", str(plan), str(stage),
            ], check=True)
            for chunk in manifest["chunks"]:
                path = stage / chunk["glb"]
                chunk["indexed_triangles"] = glb_info(path, chunk)
                chunk["sha256"] = sha256(path)
                del chunk["plan_file"]
            if manifest["landmarks"]:
                authored = stage / STATION_ASSET
                authored.parent.mkdir()
                (authored.parent / ".gdignore").touch()
                shutil.copyfile(args.station_exterior, authored)
                if sha256(authored) != manifest["landmarks"][0]["sha256"]:
                    raise ValueError("Station asset changed during the build.")
            preserve_import_settings(target, stage, manifest)
            write_json(stage / "rva_chunks.json", manifest)
            publish_snapshot(stage, target)
    print(f"Wrote {target}: {len(manifest['chunks'])} GLB chunks, "
          f"{manifest['counts']['buildings']} generic buildings, {len(manifest['landmarks'])} authored landmarks "
          f"and {len(manifest['rejected'])} rejected footprints.")


if __name__ == "__main__":
    if "--" in sys.argv and sys.argv[sys.argv.index("--") + 1:][:1] == ["--export-plan"]:
        _, plan_path, export_dir = sys.argv[sys.argv.index("--") + 1:]
        export_with_bpy(Path(plan_path), Path(export_dir))
    else:
        try:
            run_build()
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            sys.exit(f"RVA building build failed. {exc}")
