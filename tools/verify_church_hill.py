"""Run the native Church Hill smoke tests in an already built Unreal project."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


TESTS = (
    "RVA.Graybox.NightShiftNativeFlow",
    "RVA.Graybox.ChurchHillSliceNativeFlow",
)


def check_report(report):
    payload = json.loads(report.read_text(encoding="utf-8-sig"))
    entries = payload.get("tests") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError("Unreal report is missing its tests array.")

    passed = []
    problems = []
    for name in TESTS:
        matches = [row for row in entries if isinstance(row, dict) and row.get("fullTestPath") == name]
        if len(matches) != 1:
            problems.append(f"{name}: expected one result, found {len(matches)}")
            continue
        result = matches[0]
        if result.get("state") != "Success" or result.get("errors") != 0:
            problems.append(f"{name}: {result.get('state', 'unknown state')}, {result.get('errors')} errors")
            continue
        passed.append(name)
    if problems:
        raise ValueError("\n".join(problems))
    return passed


def find_editor(explicit):
    if explicit is not None:
        return explicit.resolve() if explicit.is_file() else None
    for binary in ("UnrealEditor-Cmd", "UnrealEditor-Cmd.exe", "UnrealEditor", "UnrealEditor.exe"):
        found = shutil.which(binary)
        if found:
            return Path(found).resolve()
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Built Unreal project (.uproject) with RVACivic enabled")
    parser.add_argument("--editor", type=Path, help="UnrealEditor-Cmd or UnrealEditor executable, if outside PATH")
    args = parser.parse_args(argv)

    editor = find_editor(args.editor)
    project = args.project
    missing = []
    if editor is None:
        missing.append("a valid Unreal Editor executable (--editor)")
    if project is None or project.suffix.lower() != ".uproject" or not project.is_file():
        missing.append("the built Unreal project file (--project)")
    if missing:
        print("BLOCKED: Supply " + " and ".join(missing) + ".")
        return 3

    project = project.resolve()
    report_root = project.parent / "Saved" / "Automation" / "RVA"
    try:
        report_root.mkdir(parents=True, exist_ok=True)
        destination = Path(tempfile.mkdtemp(prefix="ChurchHill-", dir=report_root))
        print(f"Unreal automation report directory: {destination}", flush=True)
        process = subprocess.run([
            str(editor), str(project), "-unattended", "-nosplash", "-nop4", "-NullRHI",
            "-stdout", "-FullStdOutLogOutput",
            "-ExecCmds=Automation RunTest " + "+".join(TESTS) + ";Quit",
            f"-ReportExportPath={destination}",
        ], timeout=900)
        if process.returncode != 0:
            print(f"FAIL: Unreal Editor exited with code {process.returncode}.")
            return 1
        for name in check_report(destination / "index.json"):
            print(f"PASS: {name}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
