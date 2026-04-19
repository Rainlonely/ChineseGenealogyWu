#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from workspace_paths import ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild glyph_image for all persons in a group from text ref boxes.")
    parser.add_argument(
        "--group-json",
        type=Path,
        required=True,
        help="Path to group_template.json",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=12,
        help="Crop padding in pixels around text box",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="PNG compression quality-like hint (0-100, higher keeps more detail)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print stats, do not write file.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_refs(person: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    text_ref = person.get("text_ref")
    if isinstance(text_ref, dict):
        refs.append(text_ref)
    text_refs = person.get("text_refs")
    if isinstance(text_refs, list):
        for ref in text_refs:
            if not isinstance(ref, dict):
                continue
            key = (ref.get("page"), ref.get("index"))
            if any((item.get("page"), item.get("index")) == key for item in refs):
                continue
            refs.append(ref)
    return refs


def to_data_url_png(image: Image.Image, *, compress_level: int) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=compress_level)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def clamp_crop_box(box: list[float], width: int, height: int, padding: int) -> tuple[int, int, int, int] | None:
    if len(box) != 4:
        return None
    x1, y1, x2, y2 = box
    values = [x1, y1, x2, y2]
    if any(not isinstance(value, (int, float)) for value in values):
        return None
    sx = max(0, int(round(min(x1, x2) - padding)))
    sy = max(0, int(round(min(y1, y2) - padding)))
    ex = min(width, int(round(max(x1, x2) + padding)))
    ey = min(height, int(round(max(y1, y2) + padding)))
    if ex - sx < 8 or ey - sy < 8:
        return None
    return sx, sy, ex, ey


def resolve_page_image_map(payload: dict[str, Any], group_json_path: Path) -> dict[int, Path]:
    page_image_map: dict[int, Path] = {}
    for entry in payload.get("pages_data", []):
        if not isinstance(entry, dict):
            continue
        page = entry.get("page")
        image = entry.get("image")
        if not isinstance(page, int) or not isinstance(image, str) or not image:
            continue
        if image.startswith("/"):
            image_path = ROOT / image.lstrip("/")
        else:
            image_path = (group_json_path.parent / image).resolve()
        page_image_map[page] = image_path
    return page_image_map


def rebuild_glyphs(group_json: Path, *, padding: int, compress_level: int, dry_run: bool) -> dict[str, int]:
    payload = load_json(group_json)
    people = payload.get("persons", [])
    if not isinstance(people, list):
        raise ValueError("Invalid group json: persons must be a list")

    page_image_map = resolve_page_image_map(payload, group_json)
    image_cache: dict[Path, Image.Image] = {}

    updated = 0
    unchanged = 0
    no_ref = 0
    bad_ref = 0
    missing_page_image = 0

    for person in people:
        if not isinstance(person, dict):
            continue
        refs = normalize_refs(person)
        if not refs:
            no_ref += 1
            continue
        target_ref = next((ref for ref in refs if isinstance(ref.get("box"), list) and ref.get("page")), None)
        if not target_ref:
            bad_ref += 1
            continue
        page = int(target_ref.get("page"))
        box = target_ref.get("box")
        image_path = page_image_map.get(page)
        if image_path is None or not image_path.exists():
            missing_page_image += 1
            continue
        if image_path not in image_cache:
            image_cache[image_path] = Image.open(image_path).convert("RGB")
        page_image = image_cache[image_path]
        crop_box = clamp_crop_box(box, page_image.width, page_image.height, padding)
        if not crop_box:
            bad_ref += 1
            continue
        cropped = page_image.crop(crop_box)
        next_glyph = to_data_url_png(cropped, compress_level=compress_level)
        current_glyph = person.get("glyph_image") if isinstance(person.get("glyph_image"), str) else ""
        if next_glyph == current_glyph:
            unchanged += 1
            continue
        person["glyph_image"] = next_glyph
        updated += 1

    if not dry_run:
        group_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for image in image_cache.values():
        image.close()

    return {
        "total_persons": len(people),
        "updated": updated,
        "unchanged": unchanged,
        "no_ref": no_ref,
        "bad_ref": bad_ref,
        "missing_page_image": missing_page_image,
    }


def main() -> None:
    args = parse_args()
    group_json = args.group_json.resolve()
    if not group_json.exists():
        raise FileNotFoundError(group_json)
    compress_level = max(0, min(9, int(round((100 - max(0, min(args.quality, 100))) / 12))))
    stats = rebuild_glyphs(
        group_json,
        padding=max(0, args.padding),
        compress_level=compress_level,
        dry_run=args.dry_run,
    )
    print(json.dumps({"group_json": str(group_json), **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
