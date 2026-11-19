# East-side pilot building footprints and heights

The western terrain pair contains 311 complete OpenStreetMap footprints. The first pass estimates heights for 270 using roof and ground returns from the same 2025 Richmond LiDAR delivery. Ten footprints use the tagged story-count estimate. The other 31 retain their geometry and an unresolved height. [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright) · [NOAA classified LiDAR](https://www.fisheries.noaa.gov/inport/item/80312/full-list)

The exporter checks all 12 locked LiDAR file hashes and compound CRS headers. Roof height uses the 95th percentile of class-6 returns inside each building. The base is the median of class-2 returns from a 0.5–8 m ring after excluding mapped buildings. Sparse roof returns, sparse ground, large local relief and implausible differences trigger a fallback. The fallback order is an explicit OSM height, then a story count at 3 m per floor plus 0.8 m, then an unresolved height.

Subtracting elevations from the same delivery cancels a shared constant offset. The export omits foundation Z until the independent DEM and LiDAR elevations have been reconciled. The roof estimate measures the upper part of the roof silhouette. Façade eaves, steeples and split-level entrances need their own measurements.

## Reproduce the export

Install `requirements-gis.txt` in a Python 3.11+ environment. Place the [locked road capture](../pilot/controls.json) in `inputs/osm_pilot.osm`, the 12 LAZ assets from [the first-pair source lock](../terrain/first_pair_sources.json) in `inputs/terrain-first-pair/`, and the [projection grids](../data/projection_lock.json) in `inputs/projection-grids/`.

```shell
python tools/run_task.py S1-02 -- python tools/pilot_building_heights.py
```

The output `outputs/pilot_building_heights.json` contains stable OSM IDs and versions, footprint polygons with holes in Unreal X/Y centimeters, height provenance and point-density and ground-relief flags. The checked-in [report](../reports/pilot_building_heights.json) records the source hashes and checks. A split of the roof samples by alternating one-meter cells gives a 0.038 m median difference across 30 buildings. This measures repeatability inside the locked cloud. Independent roof accuracy and an editor import still need verification. Building parts and architectural façade assignments are later authoring steps.
