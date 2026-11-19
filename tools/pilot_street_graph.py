"""Export the locked Richmond pilot's horizontal OSM street and footway graph."""

import argparse
from collections import Counter, defaultdict
import hashlib
import math
from pathlib import Path
import sys
from xml.etree import ElementTree

from atomic_output import write_json
from pilot_contract import ROOT, audit_osm_capture, load_json, pyproj, unreal_position


CAR_ROADS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "living_street", "service", "track",
}
FOOT_WAYS = CAR_ROADS - {"motorway", "motorway_link"} | {
    "footway", "path", "pedestrian", "steps", "cycleway",
}
ACTIVE_WAYS = CAR_ROADS | FOOT_WAYS
PUBLIC_ACCESS = {"yes", "permissive", "designated"}
DIRECTION = {"yes": (True, False), "1": (True, False), "true": (True, False),
             "-1": (False, True), "no": (True, True), "0": (True, True), "false": (True, True)}


def tags(element):
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def first_tag(properties, keys, default):
    return next((properties[key] for key in keys if key in properties), default)


def mode_access(properties, specific, default):
    for key in specific:
        if key in properties:
            return properties[key] in PUBLIC_ACCESS
    general = properties.get("access")
    return default and (general is None or general in PUBLIC_ACCESS)


def permitted_directions(properties):
    highway = properties["highway"]
    car = mode_access(properties, ("motorcar", "motor_vehicle", "vehicle"), highway in CAR_ROADS)
    foot = mode_access(properties, ("foot",), highway in FOOT_WAYS)
    implied = "yes" if highway == "motorway" or properties.get("junction") == "roundabout" else "no"
    car_rule = first_tag(properties, ("oneway:motorcar", "oneway:motor_vehicle", "oneway:vehicle", "oneway"), implied)
    foot_rule = properties.get("oneway:foot", "no")
    normal = {"car": DIRECTION.get(car_rule, (False, False)) if car else (False, False),
              "foot": DIRECTION.get(foot_rule, (False, False)) if foot else (False, False)}
    directions = []
    for index, side in enumerate(("forward", "backward")):
        modes = []
        for mode, keys in (("car", ("motorcar", "motor_vehicle", "vehicle")), ("foot", ("foot",))):
            directional = first_tag(properties, [key + ":" + side for key in (*keys, "access")], None)
            if normal[mode][index] and (directional is None or directional in PUBLIC_ACCESS):
                modes.append(mode)
        directions.append(modes)
    return directions


def infrastructure(properties, key):
    return properties.get(key, "no") not in {"no", "false", "0", ""}


def touches_bounds(start, end, bounds):
    # Keep complete OSM node pairs so intersections retain their source IDs.
    first, last = 0.0, 1.0
    for a, b, low, high in zip(start, end, bounds[:2], bounds[2:]):
        if a == b:
            if a < low or a > high:
                return False
            continue
        begin = (low - a) / (b - a)
        finish = (high - a) / (b - a)
        first = max(first, min(begin, finish))
        last = min(last, max(begin, finish))
        if first > last:
            return False
    return True


def node_rows(root, projection, origin, grid):
    nodes = {}
    for node in root.findall("node"):
        node_id = int(node.attrib["id"])
        east, north = projection.transform(float(node.attrib["lon"]), float(node.attrib["lat"]), errcheck=True)
        offsets = east - origin[0], north - origin[1]
        x, y, _ = unreal_position(grid, *offsets, grid["origin_navd88_m"])
        nodes[node_id] = {"id": node_id, "osm_version": int(node.attrib["version"]),
                          "local_en_m": [round(v, 6) for v in offsets], "unreal_xy_cm": [round(x, 4), round(y, 4)]}
    return nodes


def street_edges(root, nodes, bounds):
    result = []
    for way in sorted(root.findall("way"), key=lambda row: int(row.attrib["id"])):
        properties = tags(way)
        if properties.get("highway") not in ACTIVE_WAYS or properties.get("area") == "yes":
            continue
        forward, backward = permitted_directions(properties)
        if not (forward or backward):
            continue
        members = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        repeated = Counter()
        bridge = infrastructure(properties, "bridge")
        tunnel = infrastructure(properties, "tunnel")
        layer = int(properties.get("layer", "1" if bridge else "-1" if tunnel else "0"))
        way_id = int(way.attrib["id"])
        for a, b in zip(members, members[1:]):
            if a == b:
                continue
            pair = tuple(sorted((a, b)))
            repeated[pair] += 1
            start, end = nodes[a]["local_en_m"], nodes[b]["local_en_m"]
            length = math.dist(start, end)
            if length == 0 or not touches_bounds(start, end, bounds):
                continue
            result.append({
                "id": f"osm/{way_id}/{pair[0]}-{pair[1]}/{repeated[pair]}",
                "way": way_id, "osm_version": int(way.attrib["version"]),
                "a": a, "b": b, "length_m": round(length, 6),
                "highway": properties["highway"], "name": properties.get("name"),
                "layer": layer, "bridge": bridge, "tunnel": tunnel,
                "forward": forward, "backward": backward,
            })
    return sorted(result, key=lambda edge: edge["id"])


def arc_index(edges, mode):
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for edge in edges:
        for start, end, direction in ((edge["a"], edge["b"], "forward"), (edge["b"], edge["a"], "backward")):
            if mode in edge[direction]:
                arc = {"edge": edge["id"], "way": edge["way"], "from": start, "to": end}
                incoming[end].append(arc)
                outgoing[start].append(arc)
    return incoming, outgoing


def turn_restrictions(root, incoming, outgoing):
    blocked = []
    unresolved = []
    for relation in sorted(root.findall("relation"), key=lambda row: int(row.attrib["id"])):
        properties = tags(relation)
        if properties.get("type") != "restriction":
            continue
        car_rules = ("restriction:motorcar", "restriction:motor_vehicle", "restriction:vehicle")
        kind = first_tag(properties, (*car_rules, "restriction"), "")
        except_modes = {mode.strip() for mode in properties.get("except", "").split(";")}
        if not any(key in properties for key in car_rules) and except_modes & {"motorcar", "motor_vehicle", "vehicle"}:
            continue
        groups = defaultdict(list)
        for member in relation.findall("member"):
            groups[member.attrib["role"]].append((member.attrib["type"], int(member.attrib["ref"])))
        identity = {"relation": int(relation.attrib["id"]), "osm_version": int(relation.attrib["version"]), "kind": kind}
        via = groups["via"]
        if (len(via) != 1 or via[0][0] != "node" or not groups["from"] or not groups["to"]
                or any(t != "way" for t, _ in groups["from"] + groups["to"])):
            unresolved.append({**identity, "reason": "unsupported_member_configuration"})
            continue
        if not kind.startswith(("only_", "no_")):
            unresolved.append({**identity, "reason": "unsupported_restriction_type"})
            continue
        node = via[0][1]
        from_ways = {way for _, way in groups["from"]}
        to_ways = {way for _, way in groups["to"]}
        arrivals = [arc for arc in incoming.get(node, []) if arc["way"] in from_ways]
        departures = outgoing.get(node, [])
        if not arrivals or not any(arc["way"] in to_ways for arc in departures):
            unresolved.append({**identity, "reason": "no_matching_directed_arcs_in_clip"})
            continue
        turns = []
        for before in arrivals:
            for after in departures:
                matches = after["way"] in to_ways
                if kind in ("no_u_turn", "only_u_turn") and before["way"] == after["way"]:
                    matches = matches and before["from"] == after["to"]
                if matches == kind.startswith("no_"):
                    turns.append([before["edge"], after["edge"]])
        if not turns:
            unresolved.append({**identity, "reason": "no_turns_to_block"})
            continue
        for a, b in sorted(set(map(tuple, turns))):
            blocked.append({**identity, "via_node": node, "incoming_edge": a, "outgoing_edge": b})
    return blocked, unresolved


def build_graph(root, grid, manifest, controls):
    projection = pyproj.Transformer.from_pipeline(grid["osm_to_grid_pipeline"])
    origin = projection.transform(*grid["origin_wgs84_lon_lat"], errcheck=True)
    nodes = node_rows(root, projection, origin, grid)
    core = manifest["core_local_bounds_m"]
    halo = grid["acquisition_halo_m"]
    bounds = [core[0] - halo, core[1] - halo, core[2] + halo, core[3] + halo]
    edges = street_edges(root, nodes, bounds)
    if not edges:
        raise ValueError("No traversable street edges in the locked core bounds.")
    connected_ids = {edge[key] for edge in edges for key in ("a", "b")}
    for control in manifest["controls"]:
        node = control["osm_node"]
        if node not in connected_ids or math.dist(nodes[node]["unreal_xy_cm"], control["unreal_centimeters_xy_only"]) > 0.1:
            raise ValueError(f"Exported road control differs from the pilot lock: {node}")
    blocked, unresolved = turn_restrictions(root, *arc_index(edges, "car"))
    return {"schema_version": 1, "source": controls["capture"], "attribution": controls["attribution"],
            "license_url": controls["license_url"], "horizontal_crs": grid["horizontal_crs"],
            "origin_grid_en_m": manifest["origin_grid_m_en"], "clip_local_bounds_en_m": bounds,
            "nodes": [nodes[node_id] for node_id in sorted(connected_ids)], "edges": edges,
            "blocked_car_turns": blocked, "unresolved_turn_restrictions": unresolved}


def cross_interior(a, b, c, d):
    def determinant(start, end, point):
        return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])

    return determinant(a, b, c) * determinant(a, b, d) < 0 and determinant(c, d, a) * determinant(c, d, b) < 0


def audit_witnesses(graph, witness_lock):
    edges = {edge["id"]: edge for edge in graph["edges"]}
    nodes = {node["id"]: node["local_en_m"] for node in graph["nodes"]}
    one_way = [edge for edge in edges.values() if edge["way"] == witness_lock["one_way_way"]]
    if not one_way or any("car" not in edge["forward"] or "car" in edge["backward"] for edge in one_way):
        raise ValueError("Locked North 17th Street one-way evidence is missing or inconsistent.")
    foot_bridge = [edge for edge in edges.values() if edge["way"] == witness_lock["foot_bridge_way"]]
    if not foot_bridge or any(not edge["bridge"] or set(edge["forward"] + edge["backward"]) != {"foot"}
                              for edge in foot_bridge):
        raise ValueError("Locked Richmond Slave Trail foot bridge evidence is missing or inconsistent.")
    upper, lower = (edges[name] for name in witness_lock["separated_edges"])
    upper_nodes = {upper["a"], upper["b"]}
    lower_nodes = {lower["a"], lower["b"]}
    if (not upper["bridge"] or upper["layer"] <= lower["layer"] or upper_nodes & lower_nodes
            or not cross_interior(nodes[upper["a"]], nodes[upper["b"]], nodes[lower["a"]], nodes[lower["b"]])):
        raise ValueError("Locked East Main Street grade separation no longer matches the capture.")

    return {**witness_lock, "one_way_edge_count": len(one_way), "foot_bridge_edge_count": len(foot_bridge)}


def summarize(graph, path):
    count = Counter(mode for edge in graph["edges"] for key in ("forward", "backward") for mode in edge[key])
    return {
        "source_capture_sha256": graph["source"]["sha256"],
        "graph_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "nodes": len(graph["nodes"]), "street_edges": len(graph["edges"]), "directed_arcs": dict(count),
        "mapped_bridge_edges": sum(edge["bridge"] for edge in graph["edges"]),
        "foot_only_bridge_edges": sum(edge["bridge"] and "car" not in edge["forward"] + edge["backward"]
                                      for edge in graph["edges"]),
        "blocked_car_turns": len(graph["blocked_car_turns"]),
        "unresolved_turn_restrictions": graph["unresolved_turn_restrictions"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm-capture", type=Path, default=ROOT / "inputs/osm_pilot.osm")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/pilot_street_graph.json")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/pilot_street_graph.json")
    args = parser.parse_args()
    if pyproj is None or not args.osm_capture.is_file():
        print("BLOCKED: Install requirements-gis.txt and provide the locked OSM capture.", file=sys.stderr)
        return 3
    try:
        if args.output.resolve() == args.report.resolve() or args.osm_capture.resolve() in {
            args.report.resolve(), args.output.resolve()
        }:
            raise ValueError("The capture, graph and report must have separate paths.")
        controls = load_json(ROOT / "pilot/controls.json")
        audit_osm_capture(args.osm_capture, controls)
        graph = build_graph(ElementTree.parse(args.osm_capture).getroot(), load_json(ROOT / "pilot/grid.json"),
                            load_json(ROOT / "pilot/tile_manifest.json"), controls)
        checks = audit_witnesses(graph, load_json(ROOT / "pilot/street_witnesses.json"))
        write_json(args.output, graph)
        report = summarize(graph, args.output)
        report["verified_controls"] = 3
        report["witnesses"] = checks
        write_json(args.report, report)
    except (ElementTree.ParseError, KeyError, OSError, ValueError, pyproj.exceptions.ProjError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f'PASS: {report["nodes"]} nodes, {report["street_edges"]} edges, three locked controls, one-way street, foot bridge and grade separation.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
