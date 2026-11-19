"""Portable station geometry contract shared by Blender and Unreal Python."""

import hashlib
import json
from math import isfinite
from zipfile import ZipFile


APPROACH_ROAD = "East_Main_Approach_Road"
LEGACY_ROAD = "Roads_and_paths"
FORECOURT = "MSS Main Street forecourt"
DECKS = ("I95_West_Mainline", "I95_East_Mainline", "I95_East_Ramp", "Bellwood_Rail_Trestle")
LANDMARK = {"MSS Headhouse": "Headhouse", "MSS Clock tower": "ClockTower", FORECOURT: "Forecourt",
            "MSS Red clay hip and dormers": "Roof", "MSS Restored train shed": "TrainShed",
            "Main Street Station lettering": "StationSign"}
GROUND = {"Terrain": "Terrain", LEGACY_ROAD: "ConnectingRoads", APPROACH_ROAD: "EastMain",
          "East_Main_Approach_North_Walk": "NorthWalk", "East_Main_Approach_South_Walk": "SouthWalk",
          "East_Main_Approach_East_Station_Walk": "EastWalk"}
MESHES = {**GROUND, **LANDMARK, **{name + "_Surface": name for name in DECKS}}
REQUIRED_PROBES = {"station_crosswalk", "fifteenth_crosswalk", "fifteenth_west_crosswalk",
                   *(f"stair_tread_{step:02d}" for step in range(1, 16)),
                   *(f"{side}_join_{place}" for side in ("west", "east") for place in ("inside", "outside")),
                   *(f"{kind}_{deck}" for deck in DECKS for kind in ("crossing", "ground_below"))}
MAP_ROOT = "/Game/RVA/Tests/StationSmoke"
AXES = "centimeters: X east, Y south, Z up; RVA pilot origin"


def ue_position(point):
    east, north, up = point
    return [round(east * 100, 4), round(north * -100, 4), round(up * 100, 4)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def mesh_bounds(vertices):
    axes = tuple(zip(*vertices))
    return [[min(axis) for axis in axes], [max(axis) for axis in axes]]


def json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def read_bundle(path):
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        meshes = manifest["meshes"]
        members = ["manifest.json", *(f"{key}.json" for key in MESHES.values())]
        if (manifest["version"] != 1 or manifest["axes"] != AXES or set(meshes) != set(MESHES.values())
                or sorted(archive.namelist()) != sorted(members)):
            raise ValueError("The station package has an unexpected schema, frame or mesh list.")
        data = {}
        for key, metadata in meshes.items():
            raw = archive.read(f"{key}.json")
            if sha(raw) != metadata["sha256"]:
                raise ValueError(f"Station package mesh {key} differs from its digest.")
            mesh = json.loads(raw)
            vertices, triangles = mesh["vertices"], mesh["triangles"]
            if (not vertices or not triangles or len(triangles) != metadata["triangles"]
                    or any(len(point) != 3 or not all(isfinite(v) for v in point) for point in vertices)
                    or any(len(set(face)) != 3 or len(face) != 3 or
                           any(type(i) is not int or not 0 <= i < len(vertices) for i in face) for face in triangles)
                    or mesh_bounds(vertices) != metadata["bounds_cm"]):
                raise ValueError(f"Station package mesh {key} contains invalid geometry or bounds.")
            data[key] = mesh
        probes = manifest["probes"]
        probe_names = {row["name"] for row in probes}
        if (not REQUIRED_PROBES.issubset(probe_names) or len(probe_names) != len(probes)
                or any(row["mesh"] not in data or len(row["point_cm"]) != 3
                       or not all(isfinite(v) for v in row["point_cm"]) for row in probes)):
            raise ValueError("The station package must describe distinct, valid collision probes.")
    return manifest, data
