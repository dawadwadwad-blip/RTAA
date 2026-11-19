"""Download a local, georeferenced Richmond GIS snapshot. Run with Python 3.11+."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import email.utils
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from shapely import line_merge, make_valid, orient_polygons
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, mapping


BBOX = (-77.495, 37.515, -77.410, 37.575)
EPSG = 26918
ORIGIN_EN = (286036.805939, 4156591.390745)
PROJECTION = "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=utm +zone=18 +ellps=GRS80"
DEM = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
NAIP = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter")
ATTRIBUTIONS = {
    "vectors": "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
    "elevation": "USGS 3D Elevation Program (3DEP), The National Map",
    "imagery": "USDA National Agriculture Imagery Program (NAIP), via USGS The National Map",
}
TRANSIENT = {408, 425, 429, 500, 502, 503, 504}
SCHEMA = "rva-gis/1"
USER_AGENT = "RVA-Aggressive-Altruism-GIS/1.0 (local open-data asset builder)"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


@contextmanager
def output_lock(target):
    """Hold an OS lock for this output directory. A crashed process releases it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with (target.parent / f".{target.name}.lock").open("a+b") as file:
        if os.name == "nt":
            import msvcrt

            if file.seek(0, os.SEEK_END) == 0:
                file.write(b"\0")
                file.flush()
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(f"Another process is using {target}.") from exc
        else:
            import fcntl

            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(f"Another process is using {target}.") from exc
        yield


def check_snapshot(target, manifest_name, schema):
    """Verify ownership and recover a prior generation interrupted between renames."""
    previous = target.with_name(f".{target.name}.previous")
    if previous.exists():
        old_manifest = previous / manifest_name
        if not old_manifest.is_file() or load_json(old_manifest).get("schema") != schema:
            raise ValueError(f"Unrecognized backup directory {previous}.")
        if not target.exists():
            previous.rename(target)
        elif (target / manifest_name).is_file() and load_json(target / manifest_name).get("schema") == schema:
            shutil.rmtree(previous)
        else:
            raise ValueError(f"Could not safely restore prior generation {previous}.")
    if not target.exists() or (target.is_dir() and not any(target.iterdir())):
        return
    manifest_path = target / manifest_name
    if not manifest_path.is_file() or load_json(manifest_path).get("schema") != schema:
        raise ValueError(f"{target} already holds other files. Specify a dedicated output directory.")


def publish_snapshot(stage, target):
    """Swap a complete generation into place, keeping a recoverable previous copy."""
    if not target.exists() or (target.is_dir() and not any(target.iterdir())):
        if target.exists():
            target.rmdir()
        stage.rename(target)
        return
    previous = target.with_name(f".{target.name}.previous")
    target.rename(previous)
    try:
        stage.rename(target)
    except BaseException:
        previous.rename(target)
        raise
    shutil.rmtree(previous)


def retry_delay(retry_after, attempt):
    if retry_after:
        try:
            return max(0, int(retry_after))
        except ValueError:
            try:
                reset = email.utils.parsedate_to_datetime(retry_after)
                return max(0, (reset - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return 2 ** (attempt + 1)


def cached_download(endpoint, params, cache, refresh, suffix, validate, attempts):
    key = hashlib.sha256((endpoint + "?" + urlencode(sorted(params.items()))).encode()).hexdigest()
    saved = cache / (key + suffix)
    if saved.is_file() and not refresh:
        try:
            return validate(saved)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Ignoring invalid cached {suffix} response ({exc}).", file=sys.stderr)
    url = endpoint + "?" + urlencode(params)
    host = urlsplit(endpoint).netloc
    for attempt in range(attempts):
        temporary = None
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=105) as response, tempfile.NamedTemporaryFile(
                dir=cache, prefix=".download-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                shutil.copyfileobj(response, stream)
            result = validate(temporary)
            os.replace(temporary, saved)
            return result
        except HTTPError as exc:
            message = exc.read(220).decode("utf-8", errors="replace")
            if exc.code not in TRANSIENT or attempt + 1 == attempts:
                raise RuntimeError(f"{host} returned HTTP {exc.code}. {message}") from exc
            delay = retry_delay(exc.headers.get("Retry-After"), attempt)
        except (OSError, RuntimeError, ValueError) as exc:
            if attempt + 1 == attempts:
                raise RuntimeError(f"{host} download failed. {exc}") from exc
            delay = retry_delay(None, attempt)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        if delay > 60:
            raise RuntimeError(f"{host} asked for a retry in {delay:.0f} seconds. Run again after that interval.")
        print(f"Retrying {host} in {delay:g} seconds.", file=sys.stderr, flush=True)
        time.sleep(delay)
    raise AssertionError("download loop ended without a result")


def overpass_data(path):
    data = load_json(path)
    if not isinstance(data, dict) or "elements" not in data or data.get("remark"):
        remark = data.get("remark") if isinstance(data, dict) else str(type(data))
        raise ValueError(f"incomplete Overpass response ({remark})")
    if not isinstance(data["elements"], list):
        raise ValueError("Overpass elements must be an array")
    return data


def get_osm(bbox, endpoints, cache, refresh, snapshot):
    if snapshot:
        data = overpass_data(snapshot)
        return data["elements"], [{"input": snapshot.name, "sha256": sha256(snapshot),
                                   "timestamp": data.get("osm3s", {}).get("timestamp_osm_base")}]
    west, south, east, north = bbox
    # Short, sequential area requests keep resource use below a whole-region query.
    columns = max(1, math.ceil((east - west) / 0.045))
    rows = max(1, math.ceil((north - south) / 0.035))
    elements = {}
    sources = []
    for row in range(rows):
        for col in range(columns):
            bounds = (
                south + (north - south) * row / rows, west + (east - west) * col / columns,
                south + (north - south) * (row + 1) / rows, west + (east - west) * (col + 1) / columns,
            )
            area = ",".join(f"{v:.9f}" for v in bounds)
            query = (
                f'[out:json][timeout:70];(way["building"]({area});'
                f'relation["building"]["type"="multipolygon"]({area});'
                f'way["highway"]({area}););out meta geom qt;'
            )
            failures = []
            for endpoint in endpoints:
                try:
                    data = cached_download(endpoint, {"data": query}, cache, refresh,
                                           ".json", overpass_data, attempts=2)
                    break
                except RuntimeError as exc:
                    failures.append(str(exc))
            else:
                raise RuntimeError(f"Overpass tile {row},{col} unavailable. " + " | ".join(failures))
            stamp = data.get("osm3s", {}).get("timestamp_osm_base")
            sources.append({"endpoint": endpoint, "bbox_swen": bounds, "timestamp": stamp})
            for element in data["elements"]:
                key = (element["type"], element["id"])
                if key not in elements or element.get("version", 0) >= elements[key].get("version", 0):
                    elements[key] = element
            print(f"Overpass tile {row + 1}/{rows}, {col + 1}/{columns}: {len(data['elements'])} elements", flush=True)
    return list(elements.values()), sources


def coords(geometry):
    if not geometry or any(point is None for point in geometry):
        raise ValueError("OSM geometry is incomplete")
    return [(point["lon"], point["lat"]) for point in geometry]


def parts_of(geometry, kind):
    if geometry.geom_type == kind and not geometry.is_empty:
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from parts_of(part, kind)


def clean_polygons(geometry):
    if not geometry.is_valid:
        geometry = make_valid(geometry)
    parts = [part for part in parts_of(geometry, "Polygon") if part.area > 0]
    if not parts:
        raise ValueError("no usable polygon")
    return orient_polygons(parts[0] if len(parts) == 1 else MultiPolygon(parts))


def closed_rings(lines):
    if not lines:
        return []
    complete = [line for line in lines if line[0] == line[-1]]
    fragments = [line for line in lines if line[0] != line[-1]]
    if fragments:
        merged = line_merge(MultiLineString(fragments))
        complete += [list(line.coords) for line in parts_of(merged, "LineString")]
    if not complete or any(len(ring) < 4 or ring[0] != ring[-1] for ring in complete):
        raise ValueError("building relation has an unclosed ring")
    return complete


def relation_polygon(element, by_id):
    outer, inner, consumed = [], [], set()
    for member in element["members"]:
        if member["type"] != "way" or member["role"] not in ("", "outer", "inner"):
            continue
        reference = member["ref"]
        data = member.get("geometry") or by_id.get(("way", reference), {}).get("geometry")
        line = coords(data)
        if len(line) < 2:
            raise ValueError("building relation member has fewer than two points")
        if member["role"] == "inner":
            inner.append(line)
        else:
            outer.append(line)
            consumed.add(reference)
    shells = [Polygon(ring) for ring in closed_rings(outer)]
    holes = [[] for _ in shells]
    for ring in closed_rings(inner):
        hole = Polygon(ring)
        candidates = [i for i, shell in enumerate(shells) if shell.covers(hole)]
        if not candidates:
            raise ValueError("building courtyard is outside the shell")
        holes[min(candidates, key=lambda i: shells[i].area)].append(ring)
    polys = [Polygon(shell.exterior.coords, cutouts) for shell, cutouts in zip(shells, holes)]
    return clean_polygons(MultiPolygon(polys)), consumed


def feature(element, geometry, index=None):
    kind = element["type"]
    osm_id = element["id"]
    feature_id = f"osm/{kind}/{osm_id}"
    if index is not None:
        feature_id += f"/segment/{index}"
    return {
        "type": "Feature", "id": feature_id, "geometry": mapping(geometry),
        "properties": {"osm_id": osm_id, "osm_type": kind,
                       "osm_version": element.get("version"), "tags": element["tags"]},
    }


def vectors(elements, bbox):
    area = box(*bbox)
    project = Transformer.from_pipeline(PROJECTION)
    by_id = {(element["type"], element["id"]): element for element in elements}
    buildings, roads, rejected = [], [], []
    consumed = set()

    def is_building(tags):
        return tags.get("building", "no").lower() not in {"", "no", "0", "false"}

    for key, element in sorted(by_id.items()):
        tags = element.get("tags", {})
        if key[0] == "relation" and is_building(tags) and tags.get("type") == "multipolygon":
            try:
                geometry, members = relation_polygon(element, by_id)
                if geometry.intersects(area):
                    buildings.append((feature(element, geometry), geometry.bounds))
                    consumed.update(members)
            except (KeyError, ValueError, GEOSException) as exc:
                rejected.append({"id": f"osm/relation/{key[1]}", "reason": str(exc)})

    for key, element in sorted(by_id.items()):
        if key[0] != "way":
            continue
        tags = element.get("tags", {})
        building = is_building(tags) and key[1] not in consumed
        highway = "highway" in tags
        if not (building or highway):
            continue
        try:
            line = coords(element.get("geometry"))
        except (KeyError, ValueError) as exc:
            rejected.append({"id": f"osm/way/{key[1]}", "reason": str(exc)})
            continue
        if building:
            try:
                if len(line) < 4 or line[0] != line[-1]:
                    raise ValueError("building way is not a closed ring")
                geometry = clean_polygons(Polygon(line))
                if geometry.intersects(area):
                    buildings.append((feature(element, geometry), geometry.bounds))
            except (ValueError, GEOSException) as exc:
                rejected.append({"id": f"osm/way/{key[1]}", "reason": str(exc)})
        if highway:
            if len(set(line)) < 2:
                rejected.append({"id": f"osm/way/{key[1]}", "reason": "highway has fewer than two unique points"})
                continue
            source = LineString(line)
            ids_at = dict(zip(line, element.get("nodes", [])))
            # Preserve source-way direction after a bounding-box cut, including one-way roads.
            fragments = list(parts_of(source.intersection(area), "LineString")) if not area.covers(source) else [source]
            ordered = []
            for fragment in fragments:
                points = list(fragment.coords)
                if fragment == source:
                    position = 0
                else:
                    position = source.project(fragment.interpolate(0.25, normalized=True))
                    end = source.project(fragment.interpolate(0.75, normalized=True))
                    if end < position:
                        points.reverse()
                        position = end
                ordered.append((position, points))
            for i, (_, points) in enumerate(sorted(ordered)):
                item = feature(element, LineString(points), i if len(ordered) > 1 else None)
                item["properties"]["osm_node_ids"] = [ids_at.get(point) for point in points]
                easting, northing = project.transform(*zip(*points), errcheck=True)
                item["properties"]["centerline_local_xz_m"] = [
                    [round(e - ORIGIN_EN[0], 4), round(ORIGIN_EN[1] - n, 4)] for e, n in zip(easting, northing)
                ]
                roads.append(item)
    return buildings, roads, rejected


def align_extent(bbox, buildings):
    west, south, east, north = bbox
    for _, (w, s, e, n) in buildings:
        west, south, east, north = min(west, w), min(south, s), max(east, e), max(north, n)
    project = Transformer.from_pipeline(PROJECTION)
    # North America WGS84 → NAD83 (1) has the same zero-parameter operation as the pilot.
    # Sample the geographic perimeter before snapping the projected bounds.
    points = [(x, y) for u in np.linspace(0, 1, 33) for x, y in (
        (west + u * (east - west), south), (west + u * (east - west), north),
        (west, south + u * (north - south)), (east, south + u * (north - south)),
    )]
    x, y = project.transform(*zip(*points), errcheck=True)
    extent = (math.floor(min(x) - 12), math.floor(min(y) - 12),
              math.ceil(max(x) + 12), math.ceil(max(y) + 12))
    if extent[2] - extent[0] > 20000 or extent[3] - extent[1] > 20000:
        raise ValueError("The projected extent exceeds this central Richmond pipeline's 20 km limit.")
    return extent


def grid_for(bounds, step):
    w, s, e, n = bounds
    cols, rows = math.ceil((e - w) / step), math.ceil((n - s) / step)
    return {"bounds_en_m": bounds, "size_px": [cols, rows], "pixel_size_en_m": [(e - w) / cols, (n - s) / rows]}


def window_bounds(grid, col, row, width, height):
    w, _, _, n = grid["bounds_en_m"]
    dx, dy = grid["pixel_size_en_m"]
    return (w + col * dx, n - (row + height) * dy, w + (col + width) * dx, n - row * dy)


def tiles(grid):
    columns, rows = grid["size_px"]
    tile = 2048
    for row in range(0, rows, tile):
        for col in range(0, columns, tile):
            yield col, row, min(tile, columns - col), min(tile, rows - row)


def raster_tile(endpoint, bounds, width, height, cache, refresh, aerial):
    params = {
        "f": "image", "format": "tiff", "bbox": ",".join(f"{val:.9f}" for val in bounds),
        "bboxSR": EPSG, "imageSR": EPSG, "size": f"{width},{height}",
        "adjustAspectRatio": "false", "interpolation": "RSP_BilinearInterpolation",
        "compression": "LZ77", "pixelType": "U8" if aerial else "F32",
        "renderingRule": json.dumps({"rasterFunction": "NaturalColor" if aerial else "None"}),
    }

    def validate(path):
        with path.open("rb") as stream:
            start = stream.read(4)
            if start not in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"):
                stream.seek(0)
                raise ValueError(f"expected GeoTIFF, got {stream.read(240).decode('utf-8', 'replace')}")
        with rasterio.open(path) as dataset:
            count = 3 if aerial else 1
            if (dataset.width, dataset.height, dataset.count) != (width, height, count):
                raise ValueError(f"wrong raster dimensions or band count ({dataset.shape}, {dataset.count})")
            if dataset.crs != rasterio.crs.CRS.from_epsg(EPSG):
                raise ValueError(f"wrong raster CRS ({dataset.crs})")
            if (any(abs(x - y) > 0.015 for x, y in zip(bounds, dataset.bounds))
                    or not dataset.transform.is_rectilinear
                    or dataset.transform.a <= 0 or dataset.transform.e >= 0
                    or abs(dataset.transform.b) > 1e-9 or abs(dataset.transform.d) > 1e-9):
                raise ValueError(f"misaligned raster transform ({dataset.transform})")
            if any(dtype != ("uint8" if aerial else "float32") for dtype in dataset.dtypes):
                raise ValueError(f"wrong raster sample type ({dataset.dtypes})")
            data = dataset.read()
            if not np.all(dataset.read_masks()) or not np.isfinite(data).all():
                raise ValueError("raster contains missing samples")
            if aerial and not np.any(data):
                raise ValueError("aerial tile is entirely black")
            if not aerial and (data.min() < -100 or data.max() > 1000):
                raise ValueError("3DEP values fall outside plausible elevations for central Richmond")
            return data

    return cached_download(endpoint, params, cache, refresh, ".tif", validate, attempts=3)


def heightmap(grid, stage, cache, refresh):
    columns, rows = grid["size_px"]
    if columns * rows > 105_000_000:
        raise ValueError("DEM grid is too large. Increase --dem-step or reduce --bbox.")
    height = np.empty((rows, columns), dtype=np.float32)
    for x, y, width, count in tiles(grid):
        bounds = window_bounds(grid, x, y, width, count)
        height[y:y + count, x:x + width] = raster_tile(DEM, bounds, width, count, cache, refresh, False)[0]
        print(f"3DEP tile at pixel {x},{y} ({width} x {count})", flush=True)
    minimum, maximum = float(height.min()), float(height.max())
    step = (maximum - minimum) / 65535 if maximum > minimum else 1.0 / 65535
    codes = np.rint((height.astype(np.float64) - minimum) / step).clip(0, 65535).astype("<u2")
    Image.fromarray(codes).save(stage / "rva_heightmap.png", compress_level=4)
    codes.tofile(stage / "rva_heightmap.r16")
    grid.update({
        "png": "rva_heightmap.png", "raw_little_endian_uint16": "rva_heightmap.r16",
        "z_offset_m": minimum, "z_scale_per_code_m": step, "max_m": maximum,
        "sample_position": "pixel_center", "row_direction": "north_to_south",
        "surface_model": "linear_triangles_nw_se",
        "quantization_max_error_m": step / 2,
    })


def albedo(grid, stage, cache, refresh):
    columns, rows = grid["size_px"]
    if columns * rows > 350_000_000:
        raise ValueError("Aerial grid is too large. Increase --aerial-step or reduce --bbox.")
    scale = min(1, 2048 / max(columns, rows))
    pwidth, pheight = max(1, round(columns * scale)), max(1, round(rows * scale))
    preview = Image.new("RGB", (pwidth, pheight))
    folder = stage / "aerial"
    entries = []
    folder.mkdir()
    for x, y, width, height in tiles(grid):
        bounds = window_bounds(grid, x, y, width, height)
        data = raster_tile(NAIP, bounds, width, height, cache, refresh, True)
        rgb = Image.fromarray(np.moveaxis(data, 0, -1))
        path = folder / f"rva_aerial_albedo_r{y:05d}_c{x:05d}.png"
        rgb.save(path, compress_level=3)
        entries.append({"path": path.relative_to(stage).as_posix(), "offset_px": [x, y],
                        "size_px": [width, height], "bounds_en_m": bounds})
        px, py = round(x * pwidth / columns), round(y * pheight / rows)
        pw = round((x + width) * pwidth / columns) - px
        ph = round((y + height) * pheight / rows) - py
        if pw and ph:
            preview.paste(rgb.resize((pw, ph), Image.Resampling.LANCZOS), (px, py))
        print(f"NAIP tile at pixel {x},{y} ({width} x {height})", flush=True)
    preview.save(stage / "rva_aerial_albedo.png", compress_level=4)
    grid.update({"preview": "rva_aerial_albedo.png", "preview_size_px": [pwidth, pheight], "tiles": entries})


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/rva_gis"))
    parser.add_argument("--cache-dir", type=Path, help="Defaults to a sibling rva_gis_cache directory.")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), default=BBOX)
    parser.add_argument("--dem-step", type=float, default=2.0, help="Requested DEM spacing in meters.")
    parser.add_argument("--aerial-step", type=float, default=0.6, help="Requested RGB imagery pixel size in meters.")
    parser.add_argument("--overpass", action="append", metavar="HTTPS_URL",
                        help="Use the supplied Overpass interpreter(s), in order.")
    parser.add_argument("--osm-file", type=Path, help="Reuse an existing Overpass JSON response with full geometry.")
    parser.add_argument("--refresh", action="store_true", help="Re-download even if a validated response is cached.")
    args = parser.parse_args()
    w, s, e, n = args.bbox
    if not (-77.7 <= w < e <= -77.2 and 37.3 <= s < n <= 37.8):
        parser.error("--bbox must be an ordered rectangle near Richmond, VA.")
    if e - w > 0.16 or n - s > 0.16:
        parser.error("--bbox exceeds this pipeline's 0.16° width or height limit.")
    if not (0.75 <= args.dem_step <= 20 and 0.3 <= args.aerial_step <= 30):
        parser.error("Use DEM spacing 0.75–20 m and aerial spacing 0.3–30 m.")
    if args.overpass and any(urlsplit(u).scheme != "https" or not urlsplit(u).netloc for u in args.overpass):
        parser.error("--overpass requires an HTTPS interpreter URL.")
    return args


def main():
    args = cli()
    target = args.output_dir.resolve()
    cache = (args.cache_dir or target.with_name("rva_gis_cache")).resolve()
    if cache == target or target in cache.parents:
        raise ValueError("Keep the download cache outside the generated output directory.")
    cache.mkdir(parents=True, exist_ok=True)
    with output_lock(target):
        check_snapshot(target, "rva_gis_manifest.json", SCHEMA)
        elements, osm_sources = get_osm(args.bbox, args.overpass or OVERPASS, cache, args.refresh, args.osm_file)
        footprint_rows, roads, rejected = vectors(elements, args.bbox)
        if not footprint_rows or not roads:
            raise ValueError("The requested Richmond extent returned no usable buildings or no usable roads.")
        bounds = align_extent(args.bbox, footprint_rows)
        dem = grid_for(bounds, args.dem_step)
        aerial = grid_for(bounds, args.aerial_step)
        with tempfile.TemporaryDirectory(prefix=".rva-gis-build-", dir=target.parent) as work:
            stage = Path(work) / target.name
            stage.mkdir()
            for name, features in (
                ("buildings", [feature for feature, _ in footprint_rows]), ("roads", roads),
            ):
                write_json(stage / f"rva_{name}.geojson", {
                    "type": "FeatureCollection", "attribution": ATTRIBUTIONS["vectors"], "features": features,
                })
            heightmap(dem, stage, cache, args.refresh)
            albedo(aerial, stage, cache, args.refresh)
            files = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
            write_json(stage / "rva_gis_manifest.json", {
                "schema": SCHEMA, "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "requested_bbox_wgs84": args.bbox, "horizontal_epsg": EPSG,
                "source_projection": PROJECTION, "origin_grid_m_en": ORIGIN_EN,
                "origin_elevation_m": 0.0, "godot_axis_order": ["east", "up", "south"],
                "vertical_reference": "3DEP source elevations in meters; no vertical datum shift applied",
                "heightmap": dem, "aerial": aerial, "files_sha256": files, "attributions": ATTRIBUTIONS,
                "sources": {"overpass": osm_sources, "dem": DEM, "aerial": NAIP},
                "vectors": {
                    "building_count": len(footprint_rows), "road_count": len(roads), "rejected": rejected,
                    "geojson_geometry": "RFC 7946 WGS84 longitude, latitude",
                    "godot_road_points_property": "centerline_local_xz_m",
                },
            })
            publish_snapshot(stage, target)
    print(f"Wrote {target}: {len(footprint_rows)} footprints, {len(roads)} road segments, "
          f"{len(aerial['tiles'])} aerial tiles and {len(rejected)} rejected source features.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        sys.exit(f"RVA GIS fetch failed. {exc}")
