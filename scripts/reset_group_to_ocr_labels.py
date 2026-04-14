#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from workspace_paths import ROOT

DEFAULT_GROUP_JSON = ROOT / "gen_093_097" / "group_template.json"

COUNT_SUFFIX_RE = re.compile(r"[一二三四五六七八九十百千兩两廿卅\d]+子")
NOISE_PATTERNS = ("圖全", "卷之一系", "卷之一", "九十三世至九十七世", "快德堂", "无十三世")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset group persons from cleaned OCR labels.")
    parser.add_argument("--group-json", type=Path, default=DEFAULT_GROUP_JSON, help="Path to group_template.json")
    parser.add_argument(
        "--default-hints",
        default="93,94,95,96,97",
        help="Comma separated 5-generation hints used when page entry lacks generation_hint",
    )
    return parser


def sanitize_text(text: str) -> str:
    value = re.sub(r"\s+", "", text or "")
    if not value:
        return ""
    for noise in NOISE_PATTERNS:
        value = value.replace(noise, "")
    value = re.sub(r"^[一二三四五六七八九十百千兩两廿卅\d]+", "", value)
    value = value.replace("系", "")
    value = value.replace("全圖", "")
    value = COUNT_SUFFIX_RE.sub("", value)
    value = re.sub(r"[一二三四五六七八九十百千兩两廿卅\d]+$", "", value)
    value = value.replace("止", "")
    value = value.strip()
    if re.search(r"[世卷系圖堂]", value):
        return ""
    if value in {"", "子", "生", "月"}:
        return ""
    return value


def item_sort_key(item: dict) -> tuple[float, float]:
    x1, y1, x2, y2 = item["box"]
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return (cy, cx)


def guess_generation(box: list[int], hints: list[int]) -> int | None:
    if not hints:
        return None
    _, y1, _, y2 = box
    cy = (y1 + y2) / 2
    # Based on the observed 41-46 layout bands.
    if cy < 430:
        return hints[0]
    if cy < 760:
        return hints[1]
    if cy < 1120:
        return hints[2]
    if cy < 1460:
        return hints[3]
    return hints[4]


def build_person(page: int, ordinal: int, label: dict, hints: list[int]) -> dict:
    generation = guess_generation(label["box"], hints)
    person_id = f"p_{page}_{ordinal:03d}"
    ref = {
        "page": page,
        "index": label["index"],
        "text": label["text"],
        "raw_text": label["raw_text"],
        "box": label["box"],
        "poly": label["poly"],
    }
    return {
        "id": person_id,
        "name": label["text"],
        "generation": generation,
        "aliases": [],
        "page_sources": [page],
        "position_hints": [{"page": page, "box": label["box"]}],
        "notes": ["OCR初稿"],
        "text_ref": ref,
        "text_refs": [ref],
    }


def reset_group_people_from_ocr(group_json: Path, default_hints: list[int]) -> int:
    data = json.loads(group_json.read_text(encoding="utf-8"))
    new_people: list[dict] = []

    for page in data["pages"]:
        entry = next(item for item in data["pages_data"] if item["page"] == page)
        hints = entry.get("generation_hint") or default_hints
        labels = []
        for text_item in sorted(entry.get("text_items", []), key=item_sort_key):
            cleaned = sanitize_text(text_item.get("text", ""))
            if not cleaned:
                continue
            labels.append(
                {
                    "page": page,
                    "index": text_item["index"],
                    "text": cleaned,
                    "raw_text": text_item.get("text", ""),
                    "box": text_item.get("box", []),
                    "poly": text_item.get("poly", []),
                }
            )
        for ordinal, label in enumerate(labels, start=1):
            new_people.append(build_person(page, ordinal, label, hints))

    data["persons"] = new_people
    data["edges"] = []

    group_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(new_people)


def main() -> int:
    args = build_parser().parse_args()
    group_json = args.group_json.resolve()
    default_hints = [int(item.strip()) for item in args.default_hints.split(",") if item.strip()]
    count = reset_group_people_from_ocr(group_json, default_hints)
    print(f"reset persons={count} edges=0 -> {group_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
