import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from atomic_output import write_json


REFERENCE_BUNDLE_SHA256 = "cbb7f8614cca769ceedab61c218d71941b9493de3fe0e3009be4ebe8516d71bc"
REFERENCE_COUNTS = {"fbx": 12, "png": 28, "footprints": 4494, "lidar_matches": 4075}
REFERENCE_LENGTH = 2058.072


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read_member(archive, name):
    matches = [member for member in archive.namelist() if Path(member).name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one archive member named {name}; found {len(matches)}.")
    return archive.read(matches[0]).decode("utf-8-sig")


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def inventory(bundle, html):
    with ZipFile(bundle) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Corrupt archive member: {bad_member}")
        names = sorted(member.filename for member in archive.infolist() if not member.is_dir())
        footprints = json.loads(read_member(archive, "Richmond_OpenStreetMap_ODbL.json"))
        heights = json.loads(read_member(archive, "Richmond_2025_Roof_Heights.json"))
        site = json.loads(read_member(archive, "Site_Reference.json"))
        rows = list(csv.DictReader(io.StringIO(read_member(archive, "Route_Centerline.csv"))))

    buildings = footprints.get("buildings")
    roof_records = heights.get("heights")
    if not isinstance(buildings, list) or not isinstance(roof_records, list):
        raise ValueError("Missing footprint or roof-height records.")
    bad_roofs = [index for index, roof in enumerate(roof_records) if roof is not None and
                 (not isinstance(roof, list) or len(roof) != 3 or not all(map(number, roof))
                  or roof[0] < roof[1] or roof[1] < roof[2])]
    matches = len(roof_records) - roof_records.count(None) - len(bad_roofs)
    chainages = [float(row["chainage_m"]) for row in rows]
    if len(chainages) < 2 or not all(map(number, chainages)):
        raise ValueError("Missing or non-finite route chainage.")
    if chainages[0] != 0 or any(b <= a for a, b in zip(chainages, chainages[1:])):
        raise ValueError("Route must start at zero with strictly increasing chainage.")
    length = chainages[-1]
    checks = [
        ("height rows equal footprint count", len(roof_records) == len(buildings)),
        ("present height triples are finite and ordered", not bad_roofs),
        ("count matches reported LiDAR total", matches == heights.get("matchCount")),
        ("final chainage agrees with site metadata",
         number(site.get("routeLengthMetres")) and abs(length - site["routeLengthMetres"]) <= 0.001),
    ]
    result = {
        "bundle": {"name": bundle.name, "sha256": sha256(bundle), "members": names},
        "html": {"name": html.name, "sha256": sha256(html)} if html else None,
        "counts": {
            "fbx": sum(name.lower().endswith(".fbx") for name in names),
            "png": sum(name.lower().endswith(".png") for name in names),
            "footprints": len(buildings), "lidar_matches": matches,
            "height_records": len(roof_records), "malformed_height_records": len(bad_roofs),
            "route_vertices": len(rows),
        },
        "route_length_m": length,
        "source_notices": {"footprints": footprints.get("license"), "lidar": heights.get("url")},
        "checks": {label: bool(passed) for label, passed in checks},
    }
    reference_drift = {
        key: {"reference": expected, "observed": result["counts"][key]}
        for key, expected in REFERENCE_COUNTS.items() if result["counts"][key] != expected
    }
    if length != REFERENCE_LENGTH:
        reference_drift["route_length_m"] = {"reference": REFERENCE_LENGTH, "observed": length}
    result["reference_comparison"] = {
        "reference_sha256": REFERENCE_BUNDLE_SHA256,
        "same_bundle": result["bundle"]["sha256"] == REFERENCE_BUNDLE_SHA256,
        "metric_drift": reference_drift,
    }
    if not result["reference_comparison"]["same_bundle"]:
        print(f"Bundle differs from the reference hash; observed metric drift: {reference_drift}")
    for label, value in result["counts"].items():
        print(f"{label}={value}")
    print(f"route_length_m={length}")
    for label, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if not all(passed for _, passed in checks):
        raise ValueError("Baseline counts or chainage disagree with bundled metadata.")
    return result


def main():
    parser = argparse.ArgumentParser(description="Inspect Richmond's first-drive baseline without extracting it.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()
    if not args.bundle.exists():
        print(f"Missing baseline ZIP: {args.bundle}", file=sys.stderr)
        return 3
    html = args.html
    if html is not None and not html.exists():
        print(f"Optional comparison HTML unavailable: {html}", file=sys.stderr)
        html = None
    try:
        report = inventory(args.bundle, html)
        write_json(Path("reports/baseline.json"), report)
    except (BadZipFile, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Baseline audit failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
