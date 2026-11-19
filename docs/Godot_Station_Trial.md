# Godot station trial

The trial puts a maintenance truck on East Main Street with the textured Main Street Station, the actual street grade from the station preview, and the elevated freeway and railway. `E` arms the striper. Drive through the amber cones and follow the lane to the green cones. `R` clears the strip and restarts the work order. `C` cycles through the southwest entrance, southeast platform and driving camera. `F2` toggles lower scene resolution and disables real-time shadows in Low mode. The HUD shows live FPS while driving.

![Southwest entrance in Godot](../reports/Godot_Station_Southwest.webp)

![Southeast platform in Godot](../reports/Godot_Station_Southeast.webp)

The update uses both street views supplied by the user as visual references. The southeast view now shows the east-facing dormers, brick connector, dark roof overhang and the shed's glass band over an exposed steel trestle. Limestone segments around the lower entrance give the southwest view deeper joints and more relief. The lot, trees and trestle details are visually fitted approximations.

The driving model samples the imported road elevation as the truck moves. It uses arcade steering and stays within the short street corridor. This is a single objective adapted from *Night Shift*. The other jobs, traffic, pedestrian controls, and city streaming remain outside this trial.

## Play

- Windows 64-bit. Extract the package and run `RVA-Night-Shift.exe`.
- Linux x86-64. Run `RVA-Night-Shift.x86_64` from the release export.
- Web. Serve the contents of the web export over HTTP or HTTPS and open `index.html` in a WebGL 2 browser. The trial uses the Compatibility renderer and a single-threaded export. [Godot web export guide](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)

## Rebuild

Start with the assembled Blender scene from [East Main Street](Station_Approach_Preview.md). This exports the existing station materials and crops the surrounding terrain. The scene uses meters with the station crossing as the horizontal origin.

```sh
python tools/run_task.py S1-11 -- blender -b outputs/station-approach/RVA_Station_Approach.blend \
  --python-exit-code 1 --python tools/export_godot_station.py
godot --headless --path godot/station_trial --editor --import
godot --headless --path godot/station_trial --fixed-fps 60 --script res://verify_trial.gd
mkdir -p outputs/godot-trial/windows
godot --headless --path godot/station_trial --export-release Windows \
  "$PWD/outputs/godot-trial/windows/RVA-Night-Shift.exe"
```

The export requires Godot 4.7.2 with matching export templates. Use the existing `Linux` and `Web` presets for those targets. Blender assets use the same data as the station preview, including © OpenStreetMap contributors (ODbL 1.0) and the local NOAA/USGS terrain evidence. [Pilot data sources](Pilot_Data_Contract.md) · [Godot license](https://godotengine.org/license/)

The engine test checks the crosswalk height and westward grade, the inspection cameras, the graphics toggle, that an unarmed crossing leaves no line, that a complete pass lays all 22 meters, and that restart clears the result. The software-rendered preview and Linux export verify the scene loads. Use the weakest intended device to validate the trial goal of 720p at a steady 30 FPS while driving past the station.
