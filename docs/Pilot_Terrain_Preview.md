# Western terrain pair

The first pair uses the 2025 City of Richmond bare-earth DEM. Two 505 × 505 heightmaps share 505 exact seam samples and contain no missing vertices. The [terrain report](../reports/terrain_first_pair_dem_only_preview.json) records the raster hashes, projected bounds and import scale.

## Elevation evidence

| Comparison | Near-level samples | Median signed difference | Median absolute difference |
| --- | ---: | ---: | ---: |
| 2025 NOAA LAZ ground minus 2025 NOAA DEM | 182 | −1.334 m | 1.334 m |
| 2025 NOAA DEM minus 2019 project USGS 3DEP DEM | 130 | −0.070 m | 0.070 m |
| 2025 NOAA LAZ ground minus 2019 project USGS 3DEP DEM | 130 | −1.402 m | 1.402 m |

The USGS overlap spans 952.6 m east–west and 456.9 m north–south. Water-adjacent and sloped points are excluded by the sample checks. Where the older raster covers the site, the two DEMs agree within about 7 cm at the median sample. The older raster supplies corroboration across the pair. Its age and lack of a vertical CRS in the header limit its role as surveyed control. The LAZ discrepancy remains open. Reported roof heights are differences within the LAZ delivery and foundation elevations stay separate. [USGS 3DEP datum reference](https://www.usgs.gov/faqs/what-projection-horizontal-datum-vertical-datum-and-resolution-a-usgs-digital-elevation-model)

## Reproduce and inspect

1. Install `requirements-gis.txt`. Place the 24 inputs in the [first-pair lock](../terrain/first_pair_sources.json) in `inputs/terrain-first-pair/`. Put the files from the [projection lock](../data/projection_lock.json) in `inputs/projection-grids/`.
2. Place the [reference raster](../terrain/reference_dem.json) in `inputs/terrain-reference/`. Its locked file is 171,948,131 bytes. Keep the USGS filename.
3. From the repository root, run the DEM-only preview command.

   ```shell
   python tools/run_task.py S1-04 -- python tools/terrain_first_pair.py --dem-only-preview --reference-dem inputs/terrain-reference/USGS_1M_18_x28y416_VA_SouthamptonHenricoWMBG_2019_B19.tif
   ```

The preview writes to `outputs/terrain-first-pair-dem-preview/`. It includes two Float32 GeoTIFFs and their little-endian R16 counterparts. Landscape import uses XY and Z scales of 100 in Unreal centimeters with the north row at the top. Anchor the pair using the reported UTM bounds and pilot origin. Check orientation, shared edge and physical ride quality in the target editor. Keep LAZ-derived foundations and bridge-deck elevations out of this preview until the registration issue has an explanation and independent control.

The strict `S1-01` run uses the same source checks without `--dem-only-preview`. It writes the comparison and blocks terrain intended for joint DEM and point-cloud placement when the registration gate fails.
