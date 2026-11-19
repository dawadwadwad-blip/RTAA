"""Collect public Richmond street reference photos and detections on local disk."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import mapbox_vector_tile
from PIL import Image, ImageOps
from pyproj import Geod, Transformer


MAX_DATASET_GB = 1.5
MAX_PHOTO_BYTES = 10_000_000
MAX_PHOTOS = 2500
SPACING = 25.0
SAME_SPOT = 8.0
MIN_HEADING_DELTA = 45.0
BBOX = (-77.495, 37.515, -77.410, 37.575)
ORIGIN = (286036.805939, 4156591.390745)
PROJECT = Transformer.from_pipeline(
    "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=utm +zone=18 +ellps=GRS80"
)
GEOD = Geod(ellps="WGS84")
GRAPH = "https://graph.mapillary.com"
KARTA = ("https://api.openstreetcam.org/2.0/photo/", "https://api.kartaview.org/2.0/photo/")
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter")
TILE = "https://tiles.mapillary.com/maps/vtp/mly_map_feature_{kind}/2/14/{x}/{y}"
AGENT = "RVA-Aggressive-Altruism-Street-Refs/1.0 (local game reference collector)"
ID = re.compile(r"(mapillary|kartaview)_[0-9]+")
FIELD_NAMES = ("id", "thumb_2048_url", "quality_score", "compass_angle", "computed_compass_angle",
               "geometry", "computed_geometry", "captured_at", "creator", "camera_type", "is_pano")
SEED_PLACES = (
    ("Main Street Station", -77.4282, 37.5344), ("Church Hill", -77.4199, 37.5330),
    ("Libby Hill Park", -77.4185, 37.5268), ("Monument Avenue and Allen", -77.4636, 37.5537),
    ("Monument Avenue and Boulevard", -77.4714, 37.5578), ("The Fan", -77.4662, 37.5498),
    ("Carytown", -77.4804, 37.5522), ("West Broad Street", -77.4630, 37.5584),
    ("East Broad Street", -77.4330, 37.5400), ("Shockoe Bottom", -77.4261, 37.5313),
    ("Belle Isle", -77.4524, 37.5286), ("Belle Isle footbridge", -77.4468, 37.5319),
    ("Scott's Addition", -77.4742, 37.5681), ("Manchester", -77.4387, 37.5209),
    ("Virginia State Capitol", -77.4341, 37.5387), ("City Hall", -77.4316, 37.5407),
    ("Oregon Hill", -77.4533, 37.5401), ("Hollywood Cemetery", -77.4562, 37.5370),
    ("Jackson Ward", -77.4423, 37.5494), ("Blackwell", -77.4448, 37.5180),
)


class ServiceError(RuntimeError):
    def __init__(self, host, detail, status=None):
        self.status = status
        super().__init__(f"{host}: {detail}")


def request(url, params=None, token=None, maximum=25_000_000):
    host = urlsplit(url).hostname
    if urlsplit(url).scheme != "https" or not host:
        raise ServiceError("source", "expected an HTTPS address")
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": AGENT})
    if token:
        req.add_unredirected_header("Authorization", "OAuth " + token)
    for attempt in range(2):
        try:
            with urlopen(req, timeout=45) as response:
                data = response.read(maximum + 1)
                if len(data) > maximum:
                    raise ServiceError(host, f"response exceeded {maximum:,} bytes")
                return data
        except HTTPError as exc:
            code = exc.code
            # Respect the provider's quota and return control to the caller on throttling.
            if code not in {500, 502, 503, 504} or attempt:
                detail = exc.read(500).decode("utf-8", errors="replace")
                try:
                    message = json.loads(detail).get("error", {}).get("message", "")
                except (ValueError, AttributeError):
                    message = ""
                for secret in (token, (params or {}).get("access_token")):
                    if secret:
                        message = message.replace(secret, "[redacted]")
                retry_after = exc.headers.get("Retry-After") if code == 429 else None
                raise ServiceError(host, f"HTTP {code} {message}".strip()
                                   + (f"; retry after {retry_after}" if retry_after else ""), code) from None
        except OSError:
            if attempt:
                raise ServiceError(host, "connection failed or timed out") from None
        time.sleep(2)
    raise AssertionError("request retries exhausted")


def json_response(url, params, token=None):
    try:
        data = json.loads(request(url, params, token))
    except (ValueError, UnicodeError):
        raise ServiceError(urlsplit(url).hostname, "invalid JSON response") from None
    if not isinstance(data, dict):
        raise ServiceError(urlsplit(url).hostname, "expected a JSON object")
    return data


def local(lon, lat):
    e, n = PROJECT.transform(lon, lat, errcheck=True)
    return (e - ORIGIN[0], ORIGIN[1] - n)


def grid_heading(lon, lat, heading):
    e, s = local(lon, lat)
    next_lon, next_lat, _ = GEOD.fwd(lon, lat, heading, 20)
    ne, ns = local(next_lon, next_lat)
    return math.degrees(math.atan2(ne - e, s - ns)) % 360


def inside(lon, lat, box=BBOX):
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def box_at(lon, lat):
    # 0.009° on either side length, clipped to the Richmond boundary.
    return (max(BBOX[0], lon - 0.0045), max(BBOX[1], lat - 0.0045),
            min(BBOX[2], lon + 0.0045), min(BBOX[3], lat + 0.0045))


def anchors_from_osm(limit, errors):
    west, south, east, north = BBOX
    poi = (
        '["historic"]', '["tourism"]', '["amenity"~"^(townhall|university|theatre|marketplace|library)$"]',
        '["leisure"="park"]',
    )
    roads = ('way["highway"]["name"~"^(Monument Avenue|East Broad Street|West Broad Street|'
             'East Main Street|West Cary Street)$",i]')
    found = {}
    mid_lon, mid_lat = (west + east) / 2, (south + north) / 2
    areas = [(s, w, n, e) for w, e in ((west, mid_lon), (mid_lon, east))
             for s, n in ((south, mid_lat), (mid_lat, north))]
    for bounds in areas:
        area = "(" + ",".join(f"{v:.6f}" for v in bounds) + ")"
        selects = "".join(f'nwr{tag}["name"]{area};' for tag in poi)
        query = f"[out:json][timeout:35];({selects});out center qt;{roads}{area};out geom qt;"
        for endpoint in OVERPASS:
            try:
                response = json_response(endpoint, {"data": query})
                if response.get("remark") or not isinstance(response.get("elements"), list):
                    raise ServiceError(urlsplit(endpoint).hostname, "incomplete Overpass output")
                for row in response["elements"]:
                    key = (row["type"], row["id"])
                    if key not in found or "geometry" in row:
                        found[key] = row
                break
            except ServiceError as error:
                errors.append(f"OSM anchor area {area}: {error}")
    anchors = [(name, lon, lat, "curated Richmond anchor") for name, lon, lat in SEED_PLACES]
    used = [local(lon, lat) for _, lon, lat, _ in anchors]

    def add(name, lon, lat, source, spacing):
        if inside(lon, lat):
            xy = local(lon, lat)
            if all(math.dist(xy, existing) >= spacing for existing in used):
                anchors.append((name, lon, lat, source))
                used.append(xy)

    corridors = []
    places = []
    for row in found.values():
        tags = row.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            continue
        if "highway" in tags and row.get("geometry"):
            points = row["geometry"]
            middle = points[len(points) // 2]
            corridors.append((name, middle["lon"], middle["lat"], row["id"]))
        else:
            point = row.get("center", row)
            if "lon" not in point or "lat" not in point:
                continue
            score = 5 * bool(tags.get("wikidata")) + 3 * ("historic" in tags) + 2 * (tags.get("leisure") == "park")
            places.append((-score, name, point["lon"], point["lat"], row["id"]))
    for name, lon, lat, oid in sorted(corridors)[:400]:
        if len(anchors) >= min(limit, 34):
            break
        add(name, lon, lat, f"OSM corridor way {oid}", 230)
    for _, name, lon, lat, oid in sorted(places):
        if len(anchors) >= limit:
            break
        add(name, lon, lat, f"OSM point of interest {oid}", 165)
    return anchors[:limit]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def capture_time(value):
    n = number(value)
    if n is not None:
        return int(n * 1000 if 0 < n < 100_000_000_000 else n)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass
    return 0


def mapillary_rows(bounds, token, status, depth=0):
    fields = FIELD_NAMES if status.get("quality_field") != "unavailable" else tuple(
        field for field in FIELD_NAMES if field != "quality_score"
    )
    params = {"bbox": ",".join(f"{v:.7f}" for v in bounds),
              "fields": ",".join(fields), "limit": 250, "is_pano": "false"}
    try:
        response = json_response(GRAPH + "/images", params, token)
    except ServiceError as exc:
        if exc.status == 400 and "quality_score" in str(exc) and "quality_score" in fields:
            status["quality_field"] = "unavailable"
            return mapillary_rows(bounds, token, status, depth)
        raise
    rows = response.get("data")
    if not isinstance(rows, list):
        raise ServiceError("Mapillary", "no image list in Graph response")
    if len(rows) < 250 or depth >= 1:
        return rows
    west, south, east, north = bounds
    cx, cy = (west + east) / 2, (south + north) / 2
    for part in ((west, south, cx, cy), (cx, south, east, cy), (west, cy, cx, north), (cx, cy, east, north)):
        rows.extend(mapillary_rows(part, token, status, depth + 1))
    return rows


def first_number(*values):
    for value in values:
        n = number(value)
        if n is not None:
            return n
    return None


def candidate(row, provider, place):
    oid = str(row.get("id", ""))
    if not re.fullmatch(r"[0-9]+", oid):
        return None
    if provider == "mapillary":
        if row.get("is_pano") or row.get("camera_type") not in (None, "perspective"):
            return None
        geom = row.get("computed_geometry") or row.get("geometry") or {}
        point = geom.get("coordinates", [])
        if geom.get("type") != "Point" or len(point) < 2:
            return None
        lon, lat = map(number, point[:2])
        heading = first_number(row.get("computed_compass_angle"), row.get("compass_angle"))
        urls = [row.get("thumb_2048_url")]
        creator = row.get("creator") or {}
        user = creator.get("username") if isinstance(creator, dict) else creator
        credit = f"{user or 'Mapillary contributor'} / Mapillary"
        source = f"https://www.mapillary.com/app/?pKey={oid}"
        captured = row.get("captured_at")
        fov = None
    else:
        processing = str(row.get("autoImgProcessingStatus", "")).upper()
        if processing and processing != "FINISHED":
            return None
        projection = str(row.get("projection", "")).lower()
        fov = first_number(row.get("fieldOfView"), row.get("field_of_view"))
        if "sphere" in projection or "fisheye" in projection or (fov is not None and fov > 125):
            return None
        lon, lat = number(row.get("lng")), number(row.get("lat"))
        heading = first_number(row.get("heading"), row.get("compassAngle"))
        urls = [row.get(key) for key in ("imageProcUrl", "fileurlProc", "fileUrlProc", "imageLthUrl",
                                        "fileurlLTh", "fileUrlLTh", "imageThUrl", "fileurlTh", "fileUrlTh")]
        sequence = row.get("sequence") or {}
        seq = row.get("sequenceId") or (sequence.get("id") if isinstance(sequence, dict) else None)
        index = row.get("sequenceIndex")
        source = (f"https://kartaview.org/details/{seq}/{index}"
                  if str(seq).isdigit() and str(index).isdigit()
                  else (f"https://kartaview.org/map/@{lat},{lon},18z" if lon is not None and lat is not None
                        else "https://kartaview.org/map"))
        user = row.get("username") or (sequence.get("username") if isinstance(sequence, dict) else None)
        credit = f"{user} / © Grab and KartaView Contributors" if user else "© Grab and KartaView Contributors"
        captured = row.get("shotDate") or row.get("dateAdded")
    urls = list(dict.fromkeys(url for url in urls if isinstance(url, str) and url.startswith("https://")))
    if (lon is None or lat is None or heading is None or not 0 <= heading <= 360
            or not inside(lon, lat) or not urls):
        return None
    fov_measured = fov is not None and 35 <= fov <= 125
    return {
        "id": f"{provider}_{oid}", "provider": provider, "place": place,
        "longitude": lon, "latitude": lat, "local_xz_m": local(lon, lat),
        "heading_deg": heading % 360, "grid_heading_deg": grid_heading(lon, lat, heading),
        "camera_height_agl_m": 2.3, "pitch_deg": 0.0,
        "horizontal_fov_deg": fov if fov_measured else 75.0, "fov_estimated": not fov_measured,
        "quality_score": number(row.get("quality_score")), "captured_at_ms": capture_time(captured),
        "credit": credit, "license": "CC BY-SA 4.0", "source_url": source, "download_urls": urls,
    }


def kartaview_rows(lon, lat, state):
    params = {"lat": lat, "lng": lon, "zoomLevel": 17, "radius": 475,
              "join": "sequence", "orderBy": "id", "orderDirection": "desc"}
    endpoint = state.get("kartaview_endpoint", KARTA[0])
    try:
        response = json_response(endpoint, params)
    except ServiceError as exc:
        if endpoint != KARTA[0] or exc.status not in {None, 404, 500, 502, 503, 504}:
            raise
        endpoint = KARTA[1]
        state["kartaview_endpoint"] = endpoint
        response = json_response(endpoint, params)
    state["kartaview_endpoint"] = endpoint
    code = str(response.get("status", {}).get("apiCode", 600))
    if code not in {"600", "601", "602"}:
        raise ServiceError("KartaView", f"API code {code}")
    result = response.get("result", {})
    rows = result.get("data", []) if isinstance(result, dict) else result
    if isinstance(rows, dict):
        rows = rows.get("photos", rows.get("currentPageItems"))
    if not isinstance(rows, list):
        raise ServiceError("KartaView", "unrecognized photo response")
    return rows


def discover(anchors, token, state, errors, no_karta):
    candidates = {}
    active = {"mapillary": bool(token), "kartaview": not no_karta}
    failures = Counter()
    for place, lon, lat, _ in anchors:
        bounds = box_at(lon, lat)
        for provider in active:
            if not active[provider]:
                continue
            try:
                rows = (mapillary_rows(bounds, token, state) if provider == "mapillary"
                        else kartaview_rows(lon, lat, state))
                state[provider + "_queries_ok"] = state.get(provider + "_queries_ok", 0) + 1
                failures[provider] = 0
            except ServiceError as error:
                errors.append(f"{provider} near {place}: {error}")
                failures[provider] += 1
                if error.status in {400, 401, 403, 429} or failures[provider] >= 2:
                    active[provider] = False
                continue
            for row in rows:
                item = candidate(row, provider, place)
                if item is None or not inside(item["longitude"], item["latitude"], bounds):
                    continue
                distance = math.dist(item["local_xz_m"], local(lon, lat))
                previous = candidates.get(item["id"])
                if previous is None or distance < previous[0]:
                    candidates[item["id"]] = (distance, item)
    pools = defaultdict(list)
    for _, photo in candidates.values():
        pools[photo["place"]].append(photo)
    state["candidate_count"] = len(candidates)
    ordered = deque(deque(sorted(pool, key=lambda item: (
        -(item["quality_score"] or 0), -item["captured_at_ms"], item["id"]
    ))) for pool in pools.values())
    while ordered:
        pool = ordered.popleft()
        yield pool.popleft()
        if pool:
            ordered.append(pool)


class Locations:
    def __init__(self, previous):
        self.cells = defaultdict(list)
        self.headings = defaultdict(list)
        for photo in previous:
            self.add(photo, tuple(photo["spot_local_xz_m"]))

    @staticmethod
    def cell(point):
        return (math.floor(point[0] / SPACING), math.floor(point[1] / SPACING))

    def add(self, photo, center):
        point = tuple(photo["local_xz_m"])
        self.cells[self.cell(point)].append((point, center))
        self.headings[center].append(photo["heading_deg"])

    def select(self, photo):
        point = tuple(photo["local_xz_m"])
        x, y = self.cell(point)
        nearby = {
            center for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            for old, center in self.cells.get((x + dx, y + dy), ())
            if math.dist(point, old) < SPACING
        }
        if not nearby:
            return point
        if len(nearby) != 1:
            return None
        center = next(iter(nearby))
        previous = self.headings[center]
        if (math.dist(center, point) > SAME_SPOT or len(previous) >= 4
                or any(abs((photo["heading_deg"] - angle + 180) % 360 - 180) < MIN_HEADING_DELTA
                       for angle in previous)):
            return None
        return center


def tile_coord(lon, lat):
    n = 2 ** 14
    return (math.floor((lon + 180) / 360 * n),
            math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def tile_wgs(x, y):
    n = 2 ** 14
    return (x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))))


def prop_type(value, layer):
    if layer == "traffic_sign":
        return "traffic_sign"
    for variants, name in (
        (("street-light", "streetlight", "street-lamp"), "street_light"),
        (("fire-hydrant",), "fire_hydrant"), (("bench",), "bench"),
        (("crosswalk", "cross-walk", "zebra-crossing", "pedestrian-crossing"), "crosswalk"),
    ):
        if any(word in value for word in variants):
            return name
    return None


def map_props(anchors, token, errors):
    if not token:
        return [], 0, 0
    boxes = [box_at(lon, lat) for _, lon, lat, _ in anchors]
    tiles = set()
    for w, s, e, n in boxes:
        left, top = tile_coord(w, n)
        right, bottom = tile_coord(e, s)
        tiles.update((x, y) for x in range(left, right + 1) for y in range(top, bottom + 1))
    props = {}
    successful = 0
    attempted = 0
    for x, y in sorted(tiles):
        for kind, layer in (("point", "point"), ("traffic_sign", "traffic_sign")):
            attempted += 1
            try:
                response = request(TILE.format(kind=kind, x=x, y=y), {"access_token": token})
                layers = mapbox_vector_tile.decode(response, default_options={"y_coord_down": True})
                tile = layers.get(layer)
                if tile is None and kind == "point":
                    tile = layers.get("map_feature")
                if tile is None and layers:
                    raise ValueError("unexpected vector tile layer")
                successful += 1
            except ServiceError as exc:
                if exc.status == 404:
                    successful += 1
                    continue
                errors.append(f"Mapillary {kind} tile 14/{x}/{y}: {exc}")
                if exc.status in {401, 403, 429}:
                    return list(props.values()), successful, attempted
                continue
            except (ValueError, TypeError) as exc:
                errors.append(f"Mapillary tile 14/{x}/{y}: {exc}")
                continue
            if not tile:
                continue
            size = tile["extent"]
            for feature in tile["features"]:
                data = feature["properties"]
                value = str(data.get("value", ""))
                category = prop_type(value, layer)
                geometry = feature["geometry"]
                oid = data.get("id") or feature.get("id")
                if category is None or not oid or geometry["type"] != "Point":
                    continue
                u, v = geometry["coordinates"]
                lon, lat = tile_wgs(x + u / size, y + v / size)
                if not any(inside(lon, lat, box) for box in boxes):
                    continue
                key = f"mapillary/{layer}/{oid}"
                props[key] = {"id": key, "type": category, "class": value,
                              "longitude": lon, "latitude": lat, "local_xz_m": local(lon, lat),
                              "source": "Mapillary", "last_seen_at_ms": data.get("last_seen_at"),
                              "placement": "sample local ground and review before spawning"}
    return list(props.values()), successful, attempted


@contextmanager
def lock(root):
    with (root / ".lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def tree_size(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, payload, cap):
    temporary = path.with_suffix(".pending")
    data = (json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
    if tree_size(path.parent) + len(data) > cap:
        raise ValueError(f"Insufficient dataset budget for {path.name}.")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verified_rows(db, root):
    pending = root / "images" / ".photo.pending"
    pending.unlink(missing_ok=True)
    rows = []
    for key, status, text in db.execute("SELECT id, status, metadata FROM photos ORDER BY ordinal").fetchall():
        photo = json.loads(text)
        path = root / photo["file"]
        if not ID.fullmatch(key) or path.parent != root / "images":
            raise ValueError("Invalid image path in the resume database.")
        if not path.is_file() or (status == "pending" and digest(path) != photo["sha256"]):
            if path.is_file():
                raise ValueError(f"Pending file conflicts with its expected digest ({key}).")
            with db:
                db.execute("DELETE FROM photos WHERE id = ?", (key,))
        elif path.stat().st_size != photo["bytes"]:
            raise ValueError(f"Local photo size changed ({key}).")
        else:
            if status == "pending":
                with db:
                    db.execute("UPDATE photos SET status='ready' WHERE id=?", (key,))
            rows.append(photo)
    return rows


def download_photo(photo, room, root, db, ordinal):
    if room < 4096:
        return False
    # The network reader is bounded before any byte is written to the dataset.
    for url in photo["download_urls"]:
        try:
            data = request(url, maximum=min(room, MAX_PHOTO_BYTES))
            break
        except ServiceError as exc:
            if exc.status == 429 or url == photo["download_urls"][-1]:
                raise
    if not data:
        return False
    temp = root / "images" / ".photo.pending"
    try:
        temp.write_bytes(data)
        with Image.open(temp) as img:
            filetype = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(img.format)
            oriented = ImageOps.exif_transpose(img)
            width, height = oriented.size
        if filetype is None or max(width, height) < 640 or not 0.5 <= width / height <= 3:
            return False
        file = f"images/{photo['id']}.{filetype}"
        target = root / file
        if target.exists():
            raise ValueError(f"Image destination already exists outside the resume records: {target}")
        meta = {k: v for k, v in photo.items() if k != "download_urls"}
        meta.update(file=file, width=width, height=height, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        with db:
            db.execute("INSERT INTO photos VALUES (?, 'pending', ?, ?)",
                       (meta["id"], ordinal, json.dumps(meta, ensure_ascii=False, allow_nan=False)))
        temp.replace(target)
        with db:
            db.execute("UPDATE photos SET status='ready' WHERE id=?", (meta["id"],))
        return meta
    finally:
        temp.unlink(missing_ok=True)


def run(args, root, db, token):
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, status TEXT, ordinal INTEGER, metadata TEXT)")
    rows = verified_rows(db, root)
    seen = {row["id"] for row in rows}
    locations = Locations(rows)
    photos_bytes = sum(row["bytes"] for row in rows)
    photo_count = len(rows)
    next_ordinal = db.execute("SELECT COALESCE(MAX(ordinal),0) FROM photos").fetchone()[0] + 1
    cap = int(args.max_gb * 1_000_000_000)
    if tree_size(root) > cap:
        raise ValueError("Existing dataset exceeds the selected byte cap; use its original cap or another directory.")
    errors = []
    status = {"mapillary": "configured" if token else "MAPILLARY_TOKEN unavailable",
              "kartaview": "disabled" if args.no_kartaview else "public API"}
    for name in ("reference_cameras.pending", "rva_street_props.pending"):
        (root / name).unlink(missing_ok=True)
    anchors = anchors_from_osm(args.max_anchors, errors)
    used = tree_size(root)
    reserve = min(12_000_000, cap // 3)
    blocked_downloads = Counter()
    unavailable_downloads = set()
    db_path = root / "reference_state.sqlite3"
    db_bytes = db_path.stat().st_size
    candidates = discover(anchors, token, status, errors, args.no_kartaview) if (
        photo_count < args.max_images and used + reserve < cap
    ) else ()
    for item in candidates:
        if used + reserve >= cap or photo_count >= args.max_images:
            break
        if item["id"] in seen or item["provider"] in unavailable_downloads:
            continue
        spot = locations.select(item)
        if spot is None:
            continue
        item["spot_local_xz_m"] = spot
        try:
            photo = download_photo(item, cap - reserve - used, root, db, next_ordinal)
        except ServiceError as exc:
            blocked_downloads[str(exc)] += 1
            if exc.status == 429:
                unavailable_downloads.add(item["provider"])
            continue
        except (OSError, Image.DecompressionBombError) as exc:
            blocked_downloads[type(exc).__name__] += 1
            continue
        if photo:
            seen.add(photo["id"])
            locations.add(photo, spot)
            rows.append(photo)
            next_ordinal += 1
            new_db_bytes = db_path.stat().st_size
            used += photo["bytes"] + new_db_bytes - db_bytes
            db_bytes = new_db_bytes
            photos_bytes += photo["bytes"]
            photo_count += 1
            if photo_count % 50 == 0:
                print(f"Saved {photo_count} spaced photos ({photos_bytes / 1e6:.1f} MB)", flush=True)
    errors += [f"{message} ({count} photo requests)" for message, count in blocked_downloads.most_common(15)]
    props_path = root / "rva_street_props.json"
    props, tile_ok, tile_attempts = map_props(anchors, token, errors)
    if (not token or tile_ok < tile_attempts) and props_path.is_file():
        # A tokenless or incomplete refresh preserves prior detections.
        previous = json.loads(props_path.read_text(encoding="utf-8"))
        retained = {item["id"]: item for group in (previous["features"], props) for item in group}
        props = list(retained.values())
        status["mapillary_props_reused"] = True
    prop_data = {
        "schema": "rva-street-props/1", "origin_grid_m_en": ORIGIN,
        "source": "Mapillary vector tiles", "tile_query_boxes_deg_span_less_than": 0.01,
        "tiles_ok": tile_ok, "tiles_attempted": tile_attempts,
        "counts": dict(Counter(item["type"] for item in props)),
        "features": sorted(props, key=lambda item: item["id"]),
    }
    atomic_json(props_path, prop_data, cap)
    atomic_json(root / "reference_cameras.json", {
        "schema": "rva-street-refs/1", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bbox_wgs84": BBOX, "origin_grid_m_en": ORIGIN, "horizontal_epsg": 26918,
        "dataset_limit_bytes": cap, "total_photo_bytes": photos_bytes, "image_count": photo_count,
        "spacing_m": SPACING, "same_spot_radius_m": SAME_SPOT, "max_headings_per_spot": 4,
        "minimum_heading_separation_deg": MIN_HEADING_DELTA, "provider_status": status,
        "anchors": [{"name": a, "longitude": b, "latitude": c, "source": d} for a, b, c, d in anchors],
        "warnings": errors, "cameras": rows,
    }, cap)
    print(f"Saved {photo_count} photos and {len(props)} street props; dataset uses {tree_size(root):,}/{cap:,} bytes.")
    for error in errors[:10]:
        print(error, file=sys.stderr)
    return 0 if rows else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/rva_street_refs"))
    parser.add_argument("--max-images", type=int, default=MAX_PHOTOS)
    parser.add_argument("--max-gb", type=float, default=MAX_DATASET_GB, help="Total on-disk cap in decimal GB.")
    parser.add_argument("--max-anchors", type=int, default=56)
    parser.add_argument("--no-kartaview", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_images <= MAX_PHOTOS or not 0.005 <= args.max_gb <= MAX_DATASET_GB:
        parser.error("Use 1–2500 images and a disk cap of 0.005–1.5 GB.")
    if not 1 <= args.max_anchors <= 64:
        parser.error("Use 1–64 anchors.")
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    with lock(root):
        with sqlite3.connect(root / "reference_state.sqlite3") as db:
            return run(args, root, db, os.environ.get("MAPILLARY_TOKEN", "").strip())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        sys.exit(f"RVA street reference fetch failed. {exc}")
