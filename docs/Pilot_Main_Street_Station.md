# Main Street Station landmark

![Street-level Blender preview of the detailed Main Street Station headhouse](../reports/Main_Street_Station_Preview.webp)

The station's headhouse and forecourt have street-level exterior geometry. The two five-bay arcades have recessed glazing and joinery, stone surrounds and balustrades. Above are the clerestory, two rows of dormers, the red clay hip roof and the clock tower with four dials under a square dome. The forecourt adds brick paving, a rusticated retaining wall, steps, handrails, lamps, and a station sign. The design follows the historic survey and modern exterior references. Ornament and forecourt dimensions are approximations. [Historic American Buildings Survey](https://tile.loc.gov/storage-services/master/pnp/habshaer/va/va0500/va0562/data/va0562data.pdf) · [Virginia Department of Historic Resources](https://www.dhr.virginia.gov/historic-registers/127-0172/) · [Amtrak's station history](https://www.greatamericanstations.org/stations/richmond-main-street-station-va-rvm/)

![Entrance-level view of the station stairs, five ground-floor arches and upper loggia](../reports/Main_Street_Station_Entrance.webp)

The Roman brick, granite, roof clay and plaza pavers use original procedural color and tangent-space normal maps. The assembled scene retains the audited archive's train shed and the pilot's neighboring building volumes. [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright)

## Coordinate match

The archived FBX uses east, north and up relative to the original vehicle start. The placement script restores the original spawn offset, reconstructs the geographic coordinates and projects to the pilot UTM grid. The old and new building rings have **99.8462% intersection over union**. A local affine fit reproduces the full nonlinear projection at the old outline vertices to within **0.003 m**. These measurements describe agreement between the two footprints and projections.

The preview anchors the clock-tower base to the current DEM. The detailed headhouse follows the archived building frontage and uses a placement matrix equivalent to the Blender scene's saved position, rotation and scale. The documented overlap applies to the audited footprint outlines. The render path checks the Blender-imported extents against the published local frame, verifies that both exports use the same terrain and footprint hashes, and removes the duplicate mass.

## Build the preview

First build the [combined mesh](Pilot_Mesh_Preview.md) from the same checkout. Put the audited `Richmond_Unreal_First_Drive.zip` in `inputs/`.

```shell
python tools/run_task.py S1-06 -- python tools/plan_pilot_station.py
blender -b --factory-startup --python-exit-code 1 --python tools/render_pilot_blender.py -- \
  outputs/pilot-mesh-preview/RVA_Pilot.obj outputs/station-detail/Street.png \
  --station-bundle inputs/Richmond_Unreal_First_Drive.zip --station-alignment reports/pilot_station_alignment.json \
  --station-view street --samples 80 --save-blend outputs/station-detail/RVA_Main_Street_Station.blend \
  --station-glb outputs/station-detail/RVA_Main_Street_Station_Exterior.glb
python tools/run_task.py S1-07 -- blender -b outputs/station-detail/RVA_Main_Street_Station.blend \
  --python-exit-code 1 --python tools/verify_station_detail.py -- outputs/station-detail/RVA_Main_Street_Station_Exterior.glb
```

Use `--station-view entrance` for the close render. Add `--build-only` to export assets without rendering. Omitting `--station-view` keeps the initial archive landmark view available as a placement check.

The `.blend` opens as an assembled scene with the original material maps packed. The GLB contains five exterior assemblies and eight embedded maps, with standard glTF Y-up axes. Its origin is the southwest corner of the headhouse's main block. The sidecar JSON maps the original Blender model-local XYZ in meters to the pilot's east, north and up coordinates. Blender reopened the scene and reimported the GLB. Exterior collision, LODs, proper train deck elevations and the Unreal drive still need target-editor checks. The immediate neighboring context remains blockout geometry. [Placement evidence](../reports/pilot_station_alignment.json)
