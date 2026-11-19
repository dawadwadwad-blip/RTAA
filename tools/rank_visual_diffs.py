"""Rank local reference/render pairs and make two compact JPEG review grids."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from skimage.metrics import structural_similarity


ID = re.compile(r"(mapillary|kartaview)_\d+")
CELL = (576, 306)
PAIR_COUNT = 8


def read_manifest(path, schema):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != schema:
        raise ValueError(f"Wrong manifest schema in {path}.")
    return data


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest points outside its dataset directory.")
    return path


def open_rgb(path):
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def feature_image(image, aspect):
    width = min(image.width, round(image.height * aspect))
    height = min(image.height, round(image.width / aspect))
    size = (320, max(48, round(320 / aspect)))
    crop = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS)
    arr = np.asarray(crop.resize(size, Image.Resampling.LANCZOS))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # Reduce the effect of uniform exposure and color shifts before comparing structure.
    low, high = np.percentile(gray, (5, 95))
    if high > low + 12:
        gray = np.clip((gray.astype(np.float32) - low) * 255 / (high - low), 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def mismatch(real, rendered):
    aspect = min(3.0, max(0.5, real.width / real.height))
    a, b = feature_image(real, aspect), feature_image(rendered, aspect)
    structure = float(structural_similarity(a, b, data_range=255))
    ea, eb = cv2.Canny(a, 35, 95), cv2.Canny(b, 35, 95)
    hits_a, hits_b = np.count_nonzero(ea), np.count_nonzero(eb)
    if hits_a and hits_b:
        kernel = np.ones((7, 7), np.uint8)
        recall = np.count_nonzero(ea & cv2.dilate(eb, kernel)) / hits_a
        precision = np.count_nonzero(eb & cv2.dilate(ea, kernel)) / hits_b
        edge_match = 2 * precision * recall / max(precision + recall, 1e-9)
    else:
        edge_match = 1.0 if not hits_a and not hits_b else 0.0
    return 0.65 * (1.0 - max(0.0, structure)) + 0.35 * (1.0 - edge_match)


def fitted(canvas, image, x, y):
    preview = ImageOps.contain(image, CELL, Image.Resampling.LANCZOS)
    canvas.paste(preview, (x + (CELL[0] - preview.width) // 2, y + (CELL[1] - preview.height) // 2))


def fit_label(draw, label, font, width):
    label = " ".join(str(label).split())
    while len(label) > 6 and draw.textlength(label, font=font) > width:
        label = label[:-4] + "…"
    return label


def grid(rows, start, target):
    margin, gap, head, footer = 16, 12, 48, 55
    w = 2 * CELL[0] + 2 * margin + gap
    h = head + max(1, len(rows)) * (CELL[1] + footer) + margin
    canvas = Image.new("RGB", (w, h), "#151719")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=15)
    heading = ImageFont.load_default(size=19)
    draw.text((margin, 12), "Street reference", font=heading, fill="#ffffff")
    draw.text((margin + CELL[0] + gap, 12), "Godot render", font=heading, fill="#ffffff")
    if not rows:
        draw.text((margin, head), "No additional matched views.", font=font, fill="#ffffff")
    credits = []
    for index, (score, meta, real_path, render_path) in enumerate(rows):
        y = head + index * (CELL[1] + footer)
        right = margin + CELL[0] + gap
        draw.rectangle((margin, y, margin + CELL[0] - 1, y + CELL[1] - 1), fill="#08090a")
        draw.rectangle((right, y, right + CELL[0] - 1, y + CELL[1] - 1), fill="#08090a")
        fitted(canvas, open_rgb(real_path), margin, y)
        fitted(canvas, open_rgb(render_path), right, y)
        below = y + CELL[1] + 5
        label = f"#{start + index}  {meta.get('place', 'Richmond')}   {meta['id']}"
        credit = meta["credit"] + " · " + meta["license"]
        draw.text((margin, below), fit_label(draw, label, font, CELL[0]), font=font, fill="#ffffff")
        draw.text((margin, below + 21), fit_label(draw, credit, font, CELL[0]), font=font, fill="#e4e4e4")
        draw.text((right, below), f"Mismatch {score:.3f}   |   estimated camera pose", font=font, fill="#ffffff")
        credits.append(f"{meta['id']}: {credit}; {meta['source_url']}; scaled for review")
    exif = Image.Exif()
    exif[270] = "\n".join(credits).encode("ascii", "replace").decode("ascii")
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".jpg", delete=False) as file:
        tmp = Path(file.name)
    try:
        canvas.save(tmp, "JPEG", quality=84, optimize=True, exif=exif)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", type=Path, default=Path("outputs/rva_street_refs/reference_cameras.json"))
    parser.add_argument("--renders", type=Path, default=Path("godot/station_trial/audit_renders/render_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/rva_visual_audit"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    refs = read_manifest(args.refs, "rva-street-refs/1")
    render = read_manifest(args.renders, "rva-audit-renders/1")
    by_id = {row["id"]: row for row in refs["cameras"]}
    ranked = []
    skipped = 0
    seen = set()
    for item in render["renders"]:
        item_id = item.get("id", "")
        meta = by_id.get(item_id)
        if (meta is None or item_id in seen or not ID.fullmatch(item_id)
                or item.get("source_sha256") != meta.get("sha256")):
            skipped += 1
            continue
        a = safe_path(args.refs.parent, meta["file"])
        b = safe_path(args.renders.parent, item["file"])
        try:
            rank = mismatch(open_rgb(a), open_rgb(b))
        except (OSError, ValueError) as exc:
            print(f"Skipping {item_id}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        ranked.append((rank, meta, a, b))
        seen.add(item_id)
    if not ranked:
        raise ValueError("No reviewable pairs matched the camera IDs and reference digests.")
    ranked.sort(key=lambda row: (-row[0], row[1]["id"]))
    top = ranked[:PAIR_COUNT]
    first = min(4, (len(top) + 1) // 2)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    grid(top[:first], 1, args.output_dir / "audit_top_mismatches_1.jpg")
    grid(top[first:], first + 1, args.output_dir / "audit_top_mismatches_2.jpg")
    print(f"Scored {len(ranked)} current pairs, skipped {skipped}, and wrote {len(top)} comparisons across two JPEGs.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"RVA visual audit failed. {error}")
