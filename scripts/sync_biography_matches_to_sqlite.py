#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "genealogy.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync biography project pages and match candidates into SQLite.")
    parser.add_argument("--project-json", type=Path, required=True)
    parser.add_argument("--match-json", type=Path, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    return parser


def ensure_pages(conn: sqlite3.Connection, project: dict) -> None:
    project_id = project["project_id"]
    source_pdf = project.get("source_pdf")
    page_map = {item["page"]: item for item in project.get("pages_data", [])}
    for page in project.get("pages", []):
        page_entry = page_map.get(page, {})
        conn.execute(
            """
            INSERT INTO biography_pages (
              project_id, page_no, image_path, source_pdf, ocr_json_path, review_status, manual_notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, page_no) DO UPDATE SET
              image_path = excluded.image_path,
              source_pdf = excluded.source_pdf,
              ocr_json_path = excluded.ocr_json_path,
              review_status = excluded.review_status,
              manual_notes_json = excluded.manual_notes_json,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                project_id,
                page,
                page_entry.get("image"),
                source_pdf,
                str((ROOT / project_id / "ocr" / f"page_{page:03d}.paddleocr.json").resolve()),
                page_entry.get("review_status") or "draft",
                json.dumps(page_entry.get("manual_notes", []), ensure_ascii=False),
            ),
        )


def sync_matches(conn: sqlite3.Connection, project: dict, match_data: dict) -> int:
    project_id = project["project_id"]
    page_map = {item["page"]: item for item in project.get("pages_data", [])}
    inserted = 0
    for page in match_data.get("pages", []):
        page_no = int(page["page"])
        page_entry = page_map.get(page_no, {})
        for item in page.get("matches", []):
            person_id = item.get("recommended_person_id")
            if not person_id:
                continue
            conn.execute(
                """
                INSERT INTO person_biographies (
                  person_id, project_id, source_page_no, source_image_path, source_title_text,
                  source_columns_json, source_text_raw, source_text_linear, source_text_punctuated,
                  source_text_baihua, source_text_translation_notes, match_status, match_confidence, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_id, project_id, source_page_no) DO UPDATE SET
                  source_image_path = excluded.source_image_path,
                  source_title_text = excluded.source_title_text,
                  match_status = excluded.match_status,
                  match_confidence = excluded.match_confidence,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    person_id,
                    project_id,
                    page_no,
                    page_entry.get("image"),
                    item.get("ocr_title"),
                    "[]",
                    None,
                    None,
                    None,
                    None,
                    None,
                    f"candidate_{item.get('match_status')}",
                    item.get("ocr_score"),
                    json.dumps([], ensure_ascii=False),
                ),
            )
            inserted += 1
    return inserted


def main() -> int:
    args = build_parser().parse_args()
    project = json.loads(args.project_json.resolve().read_text(encoding="utf-8"))
    match_data = json.loads(args.match_json.resolve().read_text(encoding="utf-8"))
    conn = sqlite3.connect(str(args.db_path.resolve()))
    try:
        ensure_pages(conn, project)
        inserted = sync_matches(conn, project, match_data)
        conn.commit()
    finally:
        conn.close()
    print(f"synced_pages={len(project.get('pages', []))}")
    print(f"synced_candidate_matches={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
