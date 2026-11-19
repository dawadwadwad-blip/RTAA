# Main Street Station Unreal smoke test

This test scene brings the station exterior and its approach into Unreal at the same coordinates as the pilot. It contains a local terrain patch, connecting streets, sidewalks, the stairs, three I-95 surfaces and the Bellwood rail span. It uses gray geometry for placement and collision. The station material maps, neighboring buildings, viaduct supports and World Partition setup are outside this fixture. [East Main Street preview](Station_Approach_Preview.md) · [Terrain and axis contract](Pilot_Data_Contract.md)

## Build the station package

Rebuild the [East Main approach scene](Station_Approach_Preview.md) and save the `.blend` with the viaducts loaded. Use the station GLB's matching placement sidecar. From the repository root:

```shell
python tools/run_task.py S1-10 -- blender -b outputs/station-approach/RVA_Station_Approach.blend \
  --python-exit-code 1 --python tools/export_station_smoke.py -- \
  --frame outputs/station-detail/RVA_Main_Street_Station_Exterior.json
```

This writes `outputs/station-smoke/RVA_Station_Smoke.zip`. The exporter compares the saved scene to the audited frame and checks 46 surface heights before and after conversion to Unreal centimeters. The package preserves X east, Y south and Z up around the pilot origin. It keeps the road, sidewalk, forecourt and each elevated surface as distinct mesh assets. [Package report](../reports/station_smoke_package.json)

## Run in the target project

Use a built UE 5.6 project with Python Editor Script Plugin, Editor Scripting Utilities and Geometry Script enabled. Supply the editor executable and the `.uproject` on that machine. The runner will start Unreal, build and save a new level under `/Game/RVA/Tests/StationSmoke`, reopen it and save the collision report under the project's `Saved/Automation/RVA`. Existing levels and assets are outside its destination. [Epic's Editor Python setup](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python?application_version=5.6)

```powershell
python tools/run_task.py S1-10 -- python tools/verify_station_smoke.py --editor "C:/Program Files/Epic Games/UE_5.6/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" --project "C:/Projects/RVA/RVA.uproject"
```

The check compares imported mesh bounds to within 2.5 mm. At each probe, one downward ray ends just above the expected surface and clears it, while another ends just below and must hit. Both use the Pawn collision profile and a 1 cm height tolerance. The test separately checks the terrain below the four elevated crossings. Its meshes use static per-triangle collision. [Epic's collision trace modes](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/CollisionTraceFlag?application_version=5.6)

## Play-in-editor checks

| Pass | Check |
| --- | --- |
| Vehicle | Give the runner an existing vehicle GameMode through `--game-mode`. Locate the west and east joins from the probe coordinates in the package report. Drive both ways across each join at low speed and check wheel contact, suspension movement and the route under I-95. |
| Pedestrian | Give a new run an existing pedestrian GameMode. Walk from the bottom sidewalk up all 15 treads to the recessed doors and back down. Record any obstruction, false fall or snag at the landing. |
| Production map | Validate imported materials, simpler collision where practical, LOD changes and World Partition streaming in the pilot map. The isolated test level uses one persistent level. |
| Civic gameplay | Run the [RVACivic Church Hill smoke tests](RVA_Church_Hill_Playtest.md) in the built project. The station map covers geometry and collision. |

The ground, stair and deck probe positions passed in Blender. Unreal Editor and the built target project were unavailable for the native runs in this workspace.
