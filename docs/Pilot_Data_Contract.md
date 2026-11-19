# East-side pilot data contract

The pilot includes Shockoe Bottom, Main Street Station, St. John’s Church and the Libby Hill overlook. The original route stays a separate driving benchmark. The [coverage overlay](../pilot/coverage.geojson) opens in QGIS as WGS84 longitude/latitude. It shows the play area, 12 terrain tiles, a 100 m acquisition halo and three street controls. The west pair of adjacent tiles is the first terrain test.

| Contract | Locked choice |
|---|---|
| World frame | NAD83 / UTM 18N (EPSG:26918), east then north in meters. NAVD88 height (EPSG:5703), in meters. |
| Origin | WGS84 longitude −77.4215°, latitude 37.5315°. Easting 286036.805939 m, northing 4156591.390745 m. NAVD88 zero is world Z zero. |
| Axis convention | Unreal X is east, Y is south and Z is up. Multiply each local meter by 100 for Unreal centimeters. Keep the projected double-precision coordinates through the export. |
| Landscape | 504 × 504 m between outer vertices. Sample a one-meter city-anchored lattice with 505 vertices per side. Share sample positions across tile edges. Acquisition bounds cover the full twelve-tile rectangle plus the halo. |
| Horizontal operations | OSM uses the inverse of EPSG:1188 before UTM projection. The [projection lock](../data/projection_lock.json) pins the NOAA horizontal pipelines and four grid hashes. Disable PROJ network access during cooking and reject ballpark substitutions. |
| Vertical operations | Convert DEM height in US survey feet using exactly `1200/3937` meters per foot. The preferred NOAA LAZ delivery is already in NAVD88 meters (GEOID18). Verify the actual CRS and units before applying either rule. An ellipsoidal input requires its own geoid transformation and validation. |

The OSM transform uses a published transformation with 4 m stated accuracy. The 2 m in-engine fixture threshold compares the importer with these projected points. An absolute survey check needs an independent surveyed reference. The NOAA fixtures verify reproducible coordinate operations, and Sprint 1 compares real ground samples after reading the asset headers. [NAD83 / UTM 18N operations](https://epsg.io/26918) · [NOAA DEM](https://www.fisheries.noaa.gov/inport/item/80311/full-list) · [NOAA classified point cloud](https://www.fisheries.noaa.gov/inport/item/80312) · [PROJ datum grids](https://cdn.proj.org/)

## Control intersections

| Control | Versioned OSM node | Expected Unreal X, Y in cm |
|---|---|---|
| East Main Street at South 15th Street | [49615901, v13](https://www.openstreetmap.org/node/49615901/history) | −77544.6, −35846.3 |
| East Broad Street at North 25th Street | [49628898, v13](https://www.openstreetmap.org/node/49628898/history) | 23921.6, −992.0 |
| East Franklin Street at North 29th Street | [9785880016, v1](https://www.openstreetmap.org/node/9785880016/history) | 40031.3, 42994.3 |

The [control lock](../pilot/controls.json) records the exact query, capture SHA-256 and the incident OSM ways and their versions. These controls have XY only. Elevation comes from the DEM build. [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright)

## Reproduce the checks

Install `requirements-gis.txt` with Python 3.11+ in an existing environment or a local virtual environment. The passing reference run used pyproj 3.7.2 and PROJ 9.5.1. From the repository root:

```shell
python tools/run_task.py S0-02 -- python tools/pilot_contract.py
python tools/run_task.py S0-02 -- python -m unittest discover -s tests -v
```

For the full evidence run, pass `--proj-grid-dir PATH` with the four exact files from the projection lock and `--osm-capture PATH` when the original bound OSM response is available. A new server response may have a different hash; the versioned node and way references identify the locked control geometry. Large downloads belong in `inputs/`.

The [source catalog](../data/catalog.json) locks product choices, download URLs, roles, licenses and expected CRSs. The OSM control response and all four projection grids were downloaded and hash-checked this sprint. NOAA raster and LAZ indexes, the dated Geofabrik extract and VGIN service were verified through their published metadata. Sprint 1 records individual downloaded asset hashes, actual headers, source dates and missing tiles before cooking. Begin with the western adjacent pair to validate the seam and class-2 ground residual before processing all 12 tiles.

The [street graph](Pilot_Street_Graph.md) uses the locked capture and three controls for a first horizontal export. It keeps bridge and tunnel geometry separate from the elevation review.

The [first-pair building export](Pilot_Building_Heights.md) measures relative roof height from the locked ground and roof points in the same LiDAR delivery. Foundation elevation remains gated by the terrain comparison.

The [first-pair terrain preview](Pilot_Terrain_Preview.md) uses the 2025 DEM with an independent USGS raster comparison. The strict combined DEM and LAZ registration gate remains open.
