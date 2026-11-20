"""Build a standalone Windows playtest ZIP from one assembled East Main generation."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROJECT_TEMPLATE = ROOT / "godot/station_trial/project.godot"
SCENE = "assets/rva_gis/pilot/east_main_night_shift.tscn"
SCRIPTS = ("station_trial.gd", "tools/gis_pilot_stream.gd", "tools/gis_east_main.gd")
NOTICES = ("Godot-LICENSE.txt", "Godot-COPYRIGHT.txt")
EXE = "RVA-Streamed-Night-Shift.exe"
LAYER = re.compile(r'"res://(assets/rva_gis/pilot/cells_\d+_\d+/[\w-]+\.scn)"')
READ_ME = """RVA: Aggressive Altruism | Streamed East Main Night Shift

Extract this ZIP, then open RVA-Streamed-Night-Shift.exe.
WASD or arrow keys: drive   E: arm striper   R: restart
C: cycle station views    F2: toggle Low graphics

Drive west from 21st Street. Press E before reaching the amber cones and
stay in the starting lane through the green cones.

This prototype uses simplified building volumes outside the authored station.
Data: © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright
Terrain and aerial imagery: USGS 3DEP and the USDA National Agriculture Imagery Program.
Godot and third-party notices are in Licenses/.
"""


def stage_project(source, stage):
    scene_text = (source / SCENE).read_text(encoding="utf-8")
    layers = sorted(set(LAYER.findall(scene_text)))
    if not layers or len({Path(layer).parent for layer in layers}) != 1:
        raise ValueError("The playable scene must reference one complete streamed generation.")
    if scene_text.count('"path": "res://assets/rva_gis/pilot/') != len(layers):
        raise ValueError("Cannot read every dynamic scene path in the playable layer index.")
    models = sorted(source.glob("assets/rva_gis/meshes/*.glb"))
    for name in [SCENE, *SCRIPTS, *layers, *(path.relative_to(source) for path in models)]:
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, dest)
    settings = PROJECT_TEMPLATE.read_text(encoding="utf-8")
    settings = re.sub(r'^run/main_scene=.*$', f'run/main_scene="res://{SCENE}"', settings, flags=re.M)
    settings = settings.replace('config/name="RVA Night Shift | Godot Trial"',
                                'config/name="RVA Night Shift | Streamed East Main"')
    if "[physics]" not in settings:
        settings += '\n[physics]\n\n3d/physics_engine="Jolt Physics"\n'
    (stage / "project.godot").write_text(settings, encoding="utf-8")
    presets = (PROJECT_TEMPLATE.parent / "export_presets.cfg").read_text(encoding="utf-8")
    preset = re.sub(r'^exclude_filter=.*$', 'exclude_filter=""', presets.split("[preset.1]", 1)[0], flags=re.M)
    (stage / "export_presets.cfg").write_text(preset, encoding="utf-8")
    return len(layers)


def build(source, notices, output, godot):
    for name in NOTICES:
        if not (notices / name).is_file():
            raise FileNotFoundError(notices / name)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(prefix=".rva-export-", dir=output.parent) as folder:
        work = Path(folder)
        stage = work / "project"
        stage.mkdir()
        layers = stage_project(source, stage)
        command = [godot, "--headless", "--path", str(stage)]
        subprocess.run([*command, "--import"], check=True)
        executable = work / EXE
        subprocess.run([*command, "--export-release", "Windows", str(executable)], check=True)
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Godot did not produce a Windows executable.")
        archive = work / "windows.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.write(executable, EXE)
            for name in NOTICES:
                bundle.write(notices / name, "Licenses/" + name)
            bundle.writestr("Read Me.txt", READ_ME)
        with ZipFile(archive) as bundle:
            if bad_file := bundle.testzip():
                raise ValueError("ZIP integrity check failed for " + bad_file)
        os.link(archive, output)
    print(f"PASS: {layers} layers, Windows x86-64 export, and ZIP integrity ({output.stat().st_size:,} bytes).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT_TEMPLATE.parent)
    parser.add_argument("--godot-notices", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", default="godot")
    args = parser.parse_args()
    try:
        build(args.project.resolve(), args.godot_notices.resolve(), args.output.resolve(), args.godot)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Night Shift packaging failed. {error}\n")


if __name__ == "__main__":
    main()
