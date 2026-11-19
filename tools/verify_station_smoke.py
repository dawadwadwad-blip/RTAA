"""Run Main Street Station's native import and collision checks on a built Unreal project."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4
from zipfile import BadZipFile

from station_smoke_contract import MAP_ROOT, digest_file, read_bundle
from verify_church_hill import find_editor


ROOT = Path(__file__).resolve().parents[1]


def check_report(report, package, bundle_sha, target):
    result = json.loads(report.read_text(encoding="utf-8"))
    if result["status"] != "PASS":
        raise ValueError(result.get("error") or "Unreal did not pass the station collision checks.")
    expected = [(p["name"], p["mesh"], [p["point_cm"][2] - 1, p["point_cm"][2] + 1]) for p in package["probes"]]
    actual = [(p["name"], p["mesh"], p["height_range_cm"]) for p in result["probes"]]
    if (result["package_sha256"] != bundle_sha or result["map"] != target
            or result["mesh_count"] != len(package["meshes"]) or actual != expected):
        raise ValueError("Unreal's report does not cover every asset and probe from this station package.")
    return len(actual)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Built target Unreal project (.uproject)")
    parser.add_argument("--editor", type=Path, help="Unreal Editor executable if outside PATH")
    parser.add_argument("--bundle", type=Path, default=ROOT / "outputs/station-smoke/RVA_Station_Smoke.zip")
    parser.add_argument("--game-mode", help="Optional existing Unreal GameMode class for manual testing afterward")
    args = parser.parse_args(argv)
    editor = find_editor(args.editor)
    missing = []
    if editor is None:
        missing.append("a valid Unreal Editor executable (--editor)")
    if not args.project or args.project.suffix.lower() != ".uproject" or not args.project.is_file():
        missing.append("the target Unreal project file (--project)")
    if not args.bundle.is_file():
        missing.append("a built station package (--bundle)")
    if missing:
        print("BLOCKED: Supply " + " and ".join(missing) + ".")
        return 3

    try:
        bundle = args.bundle.resolve()
        package, _ = read_bundle(bundle)
        bundle_sha = digest_file(bundle)
        project = args.project.resolve()
        saved = project.parent / "Saved" / "Automation" / "RVA"
        saved.mkdir(parents=True, exist_ok=True)
        report_dir = Path(tempfile.mkdtemp(prefix="StationSmoke-", dir=saved))
        report = report_dir / "collision.json"
        variant = "Run_" + uuid4().hex[:12]
        script_args = [str(bundle), str(report), "--variant", variant]
        if args.game_mode:
            script_args.extend(["--game-mode", args.game_mode])
        print(f"Unreal station report directory: {report_dir}", flush=True)
        with tempfile.TemporaryDirectory() as staging:
            launcher = Path(staging) / "station_smoke_launch.py"
            launcher.write_text(f"import sys\nsys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                                f"from build_station_smoke_map import main\nmain({script_args!r})\n", encoding="utf-8")
            process = subprocess.run([str(editor), str(project), "-unattended", "-nosplash", "-nop4",
                                      "-stdout", "-FullStdOutLogOutput", f"-ExecutePythonScript={launcher}"], timeout=900)
        if not report.is_file():
            raise ValueError(f"Unreal exited with code {process.returncode} without a collision report. "
                             "Check the editor log and enabled Python, Editor Scripting Utilities and Geometry Script plugins.")
        target = f"{MAP_ROOT}/{variant}/StationSmoke"
        count = check_report(report, package, bundle_sha, target)
        if process.returncode:
            raise ValueError(f"Unreal exited with code {process.returncode} after writing its report.")
        print(f"PASS: Verified {count} native collision probes in {target}.")
    except (OSError, BadZipFile, KeyError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
