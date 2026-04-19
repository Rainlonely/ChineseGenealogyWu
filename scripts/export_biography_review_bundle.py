#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a browser-friendly review bundle for biography pages.")
    parser.add_argument("--project-json", type=Path, required=True)
    parser.add_argument("--match-json", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    return parser


def rel_to_project(project_dir: Path, target: Path | None) -> str | None:
    if target is None:
        return None
    try:
        return str(target.resolve().relative_to(project_dir.resolve()))
    except Exception:
        return str(target)


def main() -> int:
    args = build_parser().parse_args()
    project_json = args.project_json.resolve()
    project_dir = project_json.parent
    project = json.loads(project_json.read_text(encoding="utf-8"))
    match_data = json.loads(args.match_json.resolve().read_text(encoding="utf-8"))
    match_page_map = {int(item["page"]): item for item in match_data.get("pages", [])}

    pages = []
    for page_entry in project.get("pages_data", []):
        page_no = int(page_entry["page"])
        ocr_json = project_dir / "ocr" / f"page_{page_no:03d}.paddleocr.json"
        ocr_txt = project_dir / "ocr" / f"page_{page_no:03d}.paddleocr.txt"
        annotated = project_dir / "ocr" / f"page_{page_no:03d}.paddleocr.annotated.jpg"
        pages.append(
            {
                "page": page_no,
                "raw_image": rel_to_project(project_dir, Path(page_entry["image"])),
                "annotated_image": rel_to_project(project_dir, annotated if annotated.exists() else None),
                "ocr_json": rel_to_project(project_dir, ocr_json if ocr_json.exists() else None),
                "ocr_txt": rel_to_project(project_dir, ocr_txt if ocr_txt.exists() else None),
                "review_status": page_entry.get("review_status"),
                "title_candidates": page_entry.get("title_candidates", []),
                "matches": match_page_map.get(page_no, {}).get("matches", []),
                "manual_notes": page_entry.get("manual_notes", []),
            }
        )

    payload = {
        "project_id": project.get("project_id"),
        "label": project.get("label"),
        "page_range": project.get("page_range"),
        "stats": match_data.get("stats", {}),
        "person_catalog": match_data.get("person_catalog", []),
        "pages": pages,
    }
    args.out_json.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.out_json.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.out_json.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
