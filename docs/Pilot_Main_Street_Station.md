# Main Street Station landmark

![Street-level Blender preview of Main Street Station on the pilot terrain](../reports/Main_Street_Station_Preview.webp)

Main Street Station now uses the clock tower, ticket hall and train shed geometry from the audited Richmond First Drive archive. The Blender preview replaces the plain OSM building volume. The historic character comes from that existing landmark asset. Neighboring buildings remain massing models. [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright)

## Coordinate match

The archived FBX uses east, north and up relative to the original vehicle start. The placement script restores the original spawn offset, reconstructs the geographic coordinates and projects to the pilot UTM grid. The old and new building rings have **99.8462% intersection over union**. A local affine fit reproduces the full nonlinear projection at the old outline vertices to within **0.003 m**. These measurements describe agreement between the two footprints and projections.

The preview anchors the clock-tower base to the current DEM. It preserves the model's original proportions and retains the existing linked elements. The render path checks the actual imported Blender extents against the published local frame, checks that both exports use the same terrain and footprint hashes, and removes the duplicate mass only after placing the landmark.

## Build the preview

First build the [combined mesh](Pilot_Mesh_Preview.md) from the same checkout. Put the audited `Richmond_Unreal_First_Drive.zip` in `inputs/`.

```shell
python tools/run_task.py S1-06 -- python tools/plan_pilot_station.py
blender -b --factory-startup --python-exit-code 1 --python tools/render_pilot_blender.py -- outputs/pilot-mesh-preview/RVA_Pilot.obj outputs/station/Main_Street_Station.png --station-bundle inputs/Richmond_Unreal_First_Drive.zip --station-alignment reports/pilot_station_alignment.json --save-blend outputs/station/Main_Street_Station.blend
```

The optional `.blend` output opens as an assembled preview. The production collision, train deck elevations, road approach and Unreal import still require target-editor checks. [Placement evidence](../reports/pilot_station_alignment.json)
