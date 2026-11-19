import argparse
from contextlib import ExitStack
import hashlib
import math
from pathlib import Path
import shutil
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen

from atomic_output import write_json
from pilot_contract import ROOT, audit_projection_assets, load_json

try:
    import laspy
    import numpy as np
    import pyproj
    from pyproj.enums import TransformDirection
    import rasterio
    from rasterio.merge import merge
    from rasterio.transform import from_origin
    from rasterio.windows import Window
except ImportError:
    rasterio = None


SURVEY_FOOT_METRES = 1200 / 3937


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_asset(path, asset):
    return path.stat().st_size == asset["bytes"] and digest(path) == asset["sha256"]


def locate_assets(source_dir, source_lock, download):
    assets = {"dem": [], "laz": []}
    for asset in source_lock["assets"]:
        path = source_dir / asset["file"]
        if not path.exists() and download:
            source_dir.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=source_dir, delete=False) as staging:
                temporary = Path(staging.name)
            try:
                with urlopen(asset["url"], timeout=60) as response, temporary.open("wb") as sink:
                    shutil.copyfileobj(response, sink, length=1024 * 1024)
                if not verify_asset(temporary, asset):
                    raise ValueError(f'Download differs from the locked asset: {asset["file"]}')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if not path.exists():
            raise FileNotFoundError(2, "missing locked terrain asset", str(path))
        if not verify_asset(path, asset):
            raise ValueError(f"Source bytes differ from the lock: {path}")
        assets[asset["kind"]].append(path)
    return assets


def assert_compound_crs(crs, reference, name):
    actual = [part.to_epsg() for part in crs.sub_crs_list] if crs else []
    expected = [reference["horizontal_epsg"], reference["vertical_epsg"]]
    if actual != expected:
        raise ValueError(f"{name}: expected compound EPSG components {expected}, got {actual}.")


def mosaic_dem(paths, reference, native_bounds):
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(path)) for path in paths]
        for dataset in datasets:
            assert_compound_crs(pyproj.CRS.from_wkt(dataset.crs.to_wkt()), reference, dataset.name)
            if (dataset.count != 1 or dataset.res != (1.0, 1.0) or dataset.nodata != -999999
                    or not dataset.transform.is_rectilinear or dataset.transform.a <= 0 or dataset.transform.e >= 0):
                raise ValueError(f"Unexpected DEM grid, orientation or no-data value: {dataset.name}")
        data, transform = merge(datasets, bounds=native_bounds, res=(1, 1), nodata=np.nan,
                                dtype="float32", target_aligned_pixels=True)
    return data[0], transform


def bilinear(raster, transform, x, y):
    # Rasterio's affine locates corners. Shift by half a cell to sample pixel centers.
    col, row = (~transform) * (x, y)
    col, row = col - 0.5, row - 0.5
    c0, r0 = np.floor(col).astype(int), np.floor(row).astype(int)
    inside = ((c0 >= 0) & (r0 >= 0) & (c0 + 1 < raster.shape[1]) & (r0 + 1 < raster.shape[0]))
    out = np.full(col.shape, np.nan)
    c, r = c0[inside], r0[inside]
    dx, dy = col[inside] - c, row[inside] - r
    out[inside] = (
        (1 - dx) * ((1 - dy) * raster[r, c] + dy * raster[r + 1, c])
        + dx * ((1 - dy) * raster[r, c + 1] + dy * raster[r + 1, c + 1])
    )
    return out


def pair_extent(grid, manifest):
    first, second = sorted(grid["first_adjacent_tiles_en"])
    if first[1] != second[1] or second[0] != first[0] + 1:
        raise ValueError("The first terrain pair must be adjacent from west to east.")
    span = grid["tile_span_m"]
    e0, n0 = manifest["origin_grid_m_en"]
    west, south = e0 + first[0] * span, n0 + first[1] * span
    return west, south, west + 2 * span, south + span


def read_ground_candidates(paths, reference, project_xy, bounds, cell=50):
    west, south, east, north = bounds
    ground = []
    wet_cells = set()
    for path in paths:
        with laspy.open(path) as reader:
            assert_compound_crs(reader.header.parse_crs(), reference, path.name)
            for points in reader.chunk_iterator(300_000):
                classification = np.asarray(points.classification)
                mask = ((classification == 2) | (classification == 9)) & ~np.asarray(points.withheld, dtype=bool)
                raw_x, raw_y = np.asarray(points.x), np.asarray(points.y)
                mask &= ((raw_x >= west - 23) & (raw_x <= east + 23)
                         & (raw_y >= south - 23) & (raw_y <= north + 23))
                # Retain points near a fixed lattice of QA cell centers. The extra
                # margin allows for the coordinate change before final selection.
                near_center = ((abs((raw_x - west) % cell - cell / 2) <= 8)
                               & (abs((raw_y - south) % cell - cell / 2) <= 8))
                wanted = mask & (near_center | (classification == 9))
                if not np.any(wanted):
                    continue
                x, y = project_xy.transform(raw_x[wanted], raw_y[wanted], errcheck=True)
                cls = classification[wanted]
                z = np.asarray(points.z)[wanted]
                water = cls == 9
                wet_cells.update(map(tuple, np.unique(np.floor(np.column_stack(
                    (x[water], y[water])) / 10).astype(int), axis=0)))
                dry = ~water & (x >= west + 2) & (x <= east - 2) & (y >= south + 2) & (y <= north - 2)
                if np.any(dry):
                    ground.append(np.column_stack((x[dry], y[dry], z[dry])))
    if not ground:
        raise ValueError("The locked LiDAR assets contain no usable class-2 points in the pilot pair.")
    return np.concatenate(ground), wet_cells


def check_ground(points, wet_cells, native, native_transform, dem_projection, bounds, cell=50):
    west, south, _, _ = bounds
    x, y, z = points.T
    cx, cy = (x - west) / cell, (y - south) / cell
    cell_x, cell_y = np.floor(cx).astype(int), np.floor(cy).astype(int)
    distance = np.hypot(x - (west + (cell_x + 0.5) * cell), y - (south + (cell_y + 0.5) * cell))
    nx, ny = dem_projection.transform(x, y, direction=TransformDirection.INVERSE, errcheck=True)
    dem = bilinear(native, native_transform, nx, ny) * SURVEY_FOOT_METRES
    # Use a centered approximately two-metre baseline in the source raster.
    d = 1 / SURVEY_FOOT_METRES
    slope_x = (bilinear(native, native_transform, nx + d, ny) - bilinear(native, native_transform, nx - d, ny)) / (2 * d)
    slope_y = (bilinear(native, native_transform, nx, ny + d) - bilinear(native, native_transform, nx, ny - d)) / (2 * d)
    eligible = np.flatnonzero((distance <= 8) & np.isfinite(dem) & (np.hypot(slope_x, slope_y) <= 0.08))
    ordered = eligible[np.lexsort((z[eligible], y[eligible], x[eligible], distance[eligible],
                                  cell_x[eligible], cell_y[eligible]))]
    cells = {}
    for i in ordered:
        cell_id = int(cell_x[i]), int(cell_y[i])
        if cell_id in cells:
            continue
        wx, wy = math.floor(x[i] / 10), math.floor(y[i] / 10)
        if any((wx + dx, wy + dy) in wet_cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            continue
        cells[cell_id] = {"cell_en": list(cell_id), "grid_en_m": [round(float(x[i]), 3), round(float(y[i]), 3)],
                          "dem_navd88_m": round(float(dem[i]), 4), "laz_navd88_m": round(float(z[i]), 4),
                          "laz_minus_dem_m": round(float(z[i] - dem[i]), 4)}
    samples = list(cells.values())
    if len(samples) < 20:
        raise ValueError(f"Expected at least 20 distributed near-level, dry class-2 points, found {len(samples)}.")
    return samples


def residual_stats(differences):
    values = np.asarray(differences, dtype="float64")
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("Residual statistics require finite samples.")
    absolute = np.abs(values)
    return {"count": len(values), "median_signed_m": round(float(np.median(values)), 4),
            "median_absolute_m": round(float(np.median(absolute)), 4),
            "p95_absolute_m": round(float(np.quantile(absolute, 0.95)), 4),
            "maximum_absolute_m": round(float(absolute.max()), 4),
            "outliers_over_one_m": int(np.count_nonzero(absolute > 1.0)),
            "within_0_30_m_median_and_1_m_max": bool(len(values) >= 20 and np.median(absolute) <= 0.30
                                                    and absolute.max() <= 1.0)}


def compare_reference(path, reference, samples):
    if path.stat().st_size != reference["bytes"] or digest(path) != reference["sha256"]:
        raise ValueError("Reference DEM bytes differ from the locked USGS product.")
    x, y = np.asarray([sample["grid_en_m"] for sample in samples]).T
    with rasterio.open(path) as dataset:
        if (dataset.crs is None or dataset.crs.to_epsg() != reference["horizontal_epsg"]
                or dataset.count != 1 or dataset.res != (1.0, 1.0) or dataset.nodata is None
                or not dataset.transform.is_rectilinear or dataset.transform.a <= 0 or dataset.transform.e >= 0):
            raise ValueError("Unexpected horizontal CRS, null policy or grid in the USGS reference.")
        cols, rows = (~dataset.transform) * (x, y)
        left, top = max(0, math.floor(cols.min()) - 2), max(0, math.floor(rows.min()) - 2)
        right = min(dataset.width, math.ceil(cols.max()) + 2)
        bottom = min(dataset.height, math.ceil(rows.max()) + 2)
        if right <= left or bottom <= top:
            raise ValueError("The locked USGS DEM does not overlap the reference sample bounds.")
        window = Window(left, top, right - left, bottom - top)
        grid = dataset.read(1, window=window, masked=True).astype("float64").filled(np.nan)
        transform = dataset.window_transform(window)
        old_height = bilinear(grid, transform, x, y)
        slope_x = (bilinear(grid, transform, x + 1, y) - bilinear(grid, transform, x - 1, y)) / 2
        slope_y = (bilinear(grid, transform, x, y + 1) - bilinear(grid, transform, x, y - 1)) / 2
    keep = np.isfinite(old_height) & (np.hypot(slope_x, slope_y) <= 0.08)
    if keep.sum() < 20:
        raise ValueError(f"Only {keep.sum()} near-level samples overlap the USGS reference. At least 20 are required.")
    dem, laz = np.asarray([[sample["dem_navd88_m"], sample["laz_navd88_m"]] for sample in samples]).T
    old = old_height[keep]
    stats = {"asset": reference["asset"], "sha256": reference["sha256"],
             "vertical_reference": reference["product_vertical_reference"], "candidate_samples": len(samples),
             "retained_samples": int(keep.sum()),
             "sample_span_en_m": [round(float(np.ptp(values[keep])), 1) for values in (x, y)],
             "noaa_dem_minus_usgs_dem": residual_stats(dem[keep] - old),
             "noaa_laz_minus_usgs_dem": residual_stats(laz[keep] - old)}
    return stats


def height_codes(heights, grid):
    if not np.all(np.isfinite(heights)):
        raise ValueError("Output has no-data or nonfinite height samples.")
    values = grid["height_code_zero"] + np.rint((heights - grid["origin_navd88_m"]) * grid["height_codes_per_m"])
    if np.any((values < 0) | (values > 65535)):
        raise ValueError("Output elevation exceeds the Unreal Landscape encoding range.")
    return values.astype("<u2")


def write_tiles(directory, heights, codes, grid, bounds):
    west, _, _, north = bounds
    span = grid["tile_span_m"]
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    with TemporaryDirectory(dir=directory) as staging:
        root = Path(staging)
        for tile, first in enumerate((0, span)):
            name = f"Richmond_Pilot_x{tile}_y0"
            values = heights[:, first:first + span + 1]
            packed = codes[:, first:first + span + 1]
            raw = root / (name + ".r16")
            tif = root / (name + ".tif")
            packed.tofile(raw)
            crs = rasterio.crs.CRS.from_wkt(pyproj.CRS("EPSG:26918+5703").to_wkt())
            transform = from_origin(west + first - 0.5, north + 0.5, 1, 1)
            with rasterio.open(tif, "w", driver="GTiff", width=values.shape[1], height=values.shape[0],
                               count=1, dtype="float32", crs=crs, transform=transform, compress="deflate") as out:
                out.write(values.astype("float32"), 1)
                out.set_band_unit(1, "m")
                out.update_tags(AREA_OR_POINT="Point")
            results.append({"heightmap": raw.name, "heightmap_sha256": digest(raw),
                            "geotiff": tif.name, "geotiff_sha256": digest(tif),
                            "elevation_range_m": [round(float(values.min()), 3), round(float(values.max()), 3)]})
        tile_width = span + 1
        left, right = [np.fromfile(root / tile["heightmap"], dtype="<u2").reshape(tile_width, tile_width)
                       for tile in results]
        if not np.array_equal(left[:, -1], right[:, 0]):
            raise ValueError("The exported R16 files disagree along the shared seam.")
        for path in root.iterdir():
            path.replace(directory / path.name)
    return results


def cook(args):
    source_lock = load_json(ROOT / "terrain/first_pair_sources.json")
    grid = load_json(ROOT / "pilot/grid.json")
    manifest = load_json(ROOT / "pilot/tile_manifest.json")
    projection_lock = load_json(ROOT / "data/projection_lock.json")
    audit_projection_assets(args.proj_grid_dir, projection_lock)
    pipelines = {op["source_crs"]: op["pipeline"] for op in projection_lock["operations"]}
    references = source_lock["source_reference"]
    project_dem = pyproj.Transformer.from_pipeline(pipelines["EPSG:2925"])
    project_laz = pyproj.Transformer.from_pipeline(pipelines["EPSG:3748"])
    assets = locate_assets(args.source_dir, source_lock, args.download)
    bounds = pair_extent(grid, manifest)
    w, s, e, n = bounds
    halo = grid["acquisition_halo_m"]
    native_bounds = project_dem.transform_bounds(w - halo, s - halo, e + halo, n + halo,
                                                  direction=TransformDirection.INVERSE, densify_pts=21)
    native, transform = mosaic_dem(assets["dem"], references["dem"], native_bounds)
    span = grid["tile_span_m"]
    x, y = np.meshgrid(w + np.arange(2 * span + 1), n - np.arange(span + 1))
    nx, ny = project_dem.transform(x, y, direction=TransformDirection.INVERSE, errcheck=True)
    heights = bilinear(native, transform, nx, ny) * SURVEY_FOOT_METRES
    codes = height_codes(heights, grid)
    points, wet = read_ground_candidates(assets["laz"], references["laz"], project_laz, bounds)
    ground_samples = check_ground(points, wet, native, transform, project_dem, bounds)
    comparison = residual_stats([sample["laz_minus_dem_m"] for sample in ground_samples])
    reference = None
    if args.reference_dem:
        reference = compare_reference(args.reference_dem, load_json(ROOT / "terrain/reference_dem.json"), ground_samples)
    same_datum_verified = comparison["within_0_30_m_median_and_1_m_max"]
    report_prefix = {"source_asset_counts": {key: len(value) for key, value in assets.items()},
                     "source_crs": references, "source_lock_sha256": digest(ROOT / "terrain/first_pair_sources.json"),
                     "horizontal_operations": {key: pipelines[key] for key in ("EPSG:2925", "EPSG:3748")},
                     "ground_comparison": comparison, "reference_comparison": reference,
                     "lidar_dem_registration_verified": same_datum_verified}
    write_json(ROOT / "reports/terrain_datum_comparison.json", report_prefix)
    if args.dem_only_preview:
        if reference is None:
            raise ValueError("A DEM-only preview requires the locked independent USGS reference.")
        support = reference["noaa_dem_minus_usgs_dem"]
        spans = reference["sample_span_en_m"]
        if support["median_absolute_m"] > 0.30 or support["p95_absolute_m"] > 1.0 or (
                spans[0] < (e - w) / 2 or spans[1] < (n - s) / 2):
            raise ValueError("The USGS comparison does not support a DEM-only preview across the pair.")
        mode = "dem_only_preview"
    elif not same_datum_verified:
        raise ValueError(f'LAZ and DEM disagree. Median signed residual {comparison["median_signed_m"]:.4f} m. '
                         'See reports/terrain_datum_comparison.json before mixing sources.')
    else:
        mode = "lidar_dem_registration_verified"

    tiles = write_tiles(args.output, heights, codes, grid, bounds)
    report = {**report_prefix, "mode": mode,
              "tool_versions": {"numpy": np.__version__, "rasterio": rasterio.__version__,
                                "gdal": rasterio.__gdal_version__, "pyproj": pyproj.__version__,
                                "proj": pyproj.proj_version_str, "laspy": laspy.__version__},
              "pair_grid_bounds_m": list(bounds), "image_row_zero": "north", "heightmap_scale_xyz": [100, 100, 100],
              "vertices_per_side": span + 1, "unique_vertices": heights.size,
              "seam_vertices": span + 1, "max_seam_code_difference": 0, "nodata_samples": 0,
              "tiles": tiles}
    write_json(args.output / "terrain_first_pair.json", report)
    write_json(ROOT / f"reports/terrain_first_pair_{mode}.json", report)
    print(f'PASS: {mode}. {len(tiles)} heightmaps, {span+1} equal exported seam samples, no missing heights.')
    if reference:
        print(f'PASS: {reference["retained_samples"]} independent reference checks. '
              f'2025 NOAA DEM median absolute difference {reference["noaa_dem_minus_usgs_dem"]["median_absolute_m"]:.4f} m.')


def main():
    parser = argparse.ArgumentParser(description="Cook and validate the Richmond pilot's first Landscape pair.")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "inputs/terrain-first-pair")
    parser.add_argument("--proj-grid-dir", type=Path, default=ROOT / "inputs/projection-grids")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference-dem", type=Path, help="Independent USGS DEM from terrain/reference_dem.json")
    parser.add_argument("--dem-only-preview", action="store_true", help="Export a separate terrain-only rehearsal")
    parser.add_argument("--download", action="store_true", help="Fetch missing assets from the verified NOAA lock.")
    args = parser.parse_args()
    if args.dem_only_preview and args.reference_dem is None:
        print("BLOCKED: Supply the locked independent USGS reference with --reference-dem.", file=sys.stderr)
        return 3
    if args.output is None:
        destination = "terrain-first-pair-dem-preview" if args.dem_only_preview else "terrain-first-pair"
        args.output = ROOT / "outputs" / destination
    if args.output.resolve().is_relative_to((ROOT / "inputs").resolve()) or args.output.resolve().is_relative_to(
            args.source_dir.resolve()) or args.output.resolve().is_relative_to(args.proj_grid_dir.resolve()):
        parser.error("The output directory must be separate from the locked input directories.")
    if rasterio is None:
        print("Missing GIS packages. Install requirements-gis.txt.", file=sys.stderr)
        return 3
    try:
        cook(args)
    except FileNotFoundError as exc:
        print(f"Missing terrain prerequisite: {exc.filename}", file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, pyproj.exceptions.ProjError) as exc:
        print(f"Terrain build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
