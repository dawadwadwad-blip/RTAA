"""Build illustrative viaduct geometry on the station's reproducible deck profiles."""

import math

from shapely import union_all
from shapely.geometry import LineString, Point, box

from atomic_output import write_text
from build_pilot_mesh_preview import Obj, digest


MATERIALS = {
    "deck_asphalt": (0.155, 0.165, 0.174),
    "deck_ballast": (0.26, 0.24, 0.215),
    "deck_green_steel": (0.095, 0.215, 0.149),
    "deck_weathered_steel": (0.127, 0.107, 0.084),
    "deck_parapet": (0.44, 0.45, 0.405),
    "deck_pier": (0.40, 0.375, 0.335),
    "deck_marking": (0.74, 0.72, 0.60),
    "deck_edge": (0.80, 0.57, 0.12),
    "railhead": (0.32, 0.32, 0.30),
}


def transverse(rows, i):
    a = rows[max(0, i - 1)]["local_en_m"]
    b = rows[min(i + 1, len(rows) - 1)]["local_en_m"]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        raise ValueError("A viaduct cross-section has no horizontal tangent.")
    return -dy / length, dx / length


def section_vertices(obj, rows, offsets, vertical):
    sections = []
    for i, row in enumerate(rows):
        x, y = row["local_en_m"]
        nx, ny = transverse(rows, i)
        level = row["preview_deck_z_m"]
        sections.append(tuple(obj.vertex((x + nx * offset, y + ny * offset, level + z))
                              for offset, z in zip(offsets, vertical, strict=True)))
    return sections


def box_ribbon(obj, rows, left, right, below, top, material):
    obj.material(material)
    rings = section_vertices(obj, rows, (left, right, right, left), (below, below, top, top))
    obj.face(tuple(reversed(rings[0])))
    for a, b in zip(rings[:-1], rings[1:], strict=True):
        for i in range(4):
            j = (i + 1) % 4
            obj.face((a[i], a[j], b[j], b[i]))
    obj.face(rings[-1])


def stripe(obj, rows, lateral, kind, dashed=False):
    obj.material(kind)
    sections = section_vertices(obj, rows, (lateral - 0.055, lateral + 0.055), (0.016, 0.016))
    for i, (a, b) in enumerate(zip(sections[:-1], sections[1:], strict=True)):
        if not dashed or i % 3 == 0:
            obj.face((a[0], b[0], b[1], a[1]))


def column(obj, x, y, base, top, width):
    obj.material("deck_pier")
    ring = [(x + sx * width / 2, y + sy * width / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bottom = [obj.vertex((*p, base)) for p in ring]
    ceiling = [obj.vertex((*p, top)) for p in ring]
    for i in range(4):
        j = (i + 1) % 4
        obj.face((bottom[i], bottom[j], ceiling[j], ceiling[i]))
    obj.face(ceiling)


def assemble(output, profiles, ground_roads, terrain):
    clip = box(-815, 207, -645, 468)
    road_exclusion = union_all([road.intersection(clip) for road in ground_roads if road.intersects(clip)]).buffer(6.5)
    rail = next(profile for profile in profiles if profile["kind"] == "rail")
    lower_deck = LineString([row["local_en_m"] for row in rail["samples"]]).buffer(5.4)
    obj = Obj("RVA_Station_Decks.mtl")
    supports = {}
    for profile in profiles:
        rows = profile["samples"]
        name, kind = profile["name"], profile["kind"]
        half = profile["illustrative_width_m"] / 2
        obj.group(name + "_Surface")
        is_rail = kind == "rail"
        steel = "deck_weathered_steel" if is_rail else "deck_green_steel"
        depth = 0.88 if is_rail else 1.35
        box_ribbon(obj, rows, -half, half, -0.27, 0.0, "deck_ballast" if is_rail else "deck_asphalt")
        for side in (-1, 1):
            edge = side * (half - 0.28)
            box_ribbon(obj, rows, edge - 0.28, edge + 0.28, -depth, -0.23, steel)
            if is_rail:
                inner = side * 0.718
                box_ribbon(obj, rows, inner - 0.045, inner + 0.045, 0.0, 0.12, "railhead")
            else:
                box_ribbon(obj, rows, edge - 0.24, edge + 0.24, -0.11, 0.88, "deck_parapet")
                stripe(obj, rows, side * (half - 0.70), "deck_edge" if side < 0 else "deck_marking")
        if kind == "road":
            for lateral in (-half / 3, half / 3):
                stripe(obj, rows, lateral, "deck_marking", dashed=True)
        obj.group(name + "_Illustrative_Supports")
        count = 0
        # Space the visual supports away from mapped at-grade travel and from
        # the lower rail deck. The cuts never define engineering pier locations.
        for row in rows[3:-2:5 if is_rail else 7]:
            x, y = row["local_en_m"]
            point = Point(x, y)
            if road_exclusion.covers(point) or (not is_rail and lower_deck.covers(point)):
                continue
            base, top = terrain.height(x, y) - 0.35, row["preview_deck_z_m"] - 0.22
            if top - base >= 2.0:
                column(obj, x, y, base, top, 2.1 if is_rail else 2.45)
                count += 1
        supports[name] = count
    mesh = output / "RVA_Station_Decks.obj"
    material = output / "RVA_Station_Decks.mtl"
    write_text(mesh, "\n".join(obj.lines) + "\n")
    write_text(material, "\n\n".join(f"newmtl {name}\nKd {r} {g} {b}\nKs 0.1 0.1 0.1\nNs 21"
                                         for name, (r, g, b) in MATERIALS.items()) + "\n")
    return {"mesh": mesh.name, "sha256": digest(mesh), "material": material.name, "material_sha256": digest(material),
            "faces": obj.faces, "vertices": obj.vertices, "illustrative_support_counts": supports,
            "scope": "visual profile mesh; widths, railheads, girders, barriers, stripes and supports are illustrative"}
