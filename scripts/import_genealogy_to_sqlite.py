from __future__ import annotations

import argparse
import base64
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DEFAULT_DB_PATH = ROOT / "data" / "genealogy.sqlite"


def parse_group_range(group_id: str) -> tuple[int, int]:
    parts = group_id.split("_")
    if len(parts) != 3:
        return (9999, 9999)
    try:
        return (int(parts[1]), int(parts[2]))
    except ValueError:
        return (9999, 9999)


def discover_group_jsons(root: Path = ROOT) -> list[Path]:
    paths = [path for path in root.glob("gen_*/*") if path.name == "group_template.json"]
    return sorted(
        paths,
        key=lambda path: (
            *parse_group_range(path.parent.name),
            path.parent.name,
        ),
    )


def discover_bridge_jsons(root: Path = ROOT) -> list[Path]:
    return sorted((root / "bridges").glob("*.json"))


DEFAULT_GROUP_JSONS = discover_group_jsons()
DEFAULT_BRIDGE_JSONS = discover_bridge_jsons()


def json_text(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def decode_data_url(data_url: str) -> tuple[str, bytes] | None:
    if not data_url.startswith("data:") or ";base64," not in data_url:
        return None
    header, payload = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0]
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime, "bin")
    return extension, base64.b64decode(payload)


def export_glyph(person_id: str, glyph_value: str | None, out_dir: Path) -> str | None:
    if not glyph_value:
        return None
    decoded = decode_data_url(glyph_value)
    if not decoded:
        return glyph_value
    extension, payload = decoded
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{person_id}.{extension}"
    target.write_bytes(payload)
    return str(target.relative_to(ROOT))


def pick_primary_ref(person: dict[str, Any]) -> dict[str, Any]:
    if isinstance(person.get("text_ref"), dict):
      return person["text_ref"]
    text_refs = person.get("text_refs") or []
    if text_refs:
      return text_refs[0]
    position_hints = person.get("position_hints") or []
    if position_hints:
      return position_hints[0]
    return {}


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def insert_group(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    pages = payload.get("pages") or []
    conn.execute(
        """
        INSERT INTO groups (
          id, label, page_start, page_end, source_pdf, raw_images_dir, cropped_images_dir, notes_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          label = excluded.label,
          page_start = excluded.page_start,
          page_end = excluded.page_end,
          source_pdf = excluded.source_pdf,
          raw_images_dir = excluded.raw_images_dir,
          cropped_images_dir = excluded.cropped_images_dir,
          notes_json = excluded.notes_json,
          status = excluded.status,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            payload["group_id"],
            payload.get("label"),
            min(pages) if pages else None,
            max(pages) if pages else None,
            payload.get("source_pdf"),
            payload.get("raw_images_dir"),
            payload.get("cropped_images_dir"),
            json_text(payload.get("notes", [])),
            "active",
        ),
    )


def insert_pages(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    page_entries = {item["page"]: item for item in payload.get("pages_data", [])}
    for page in payload.get("pages", []):
        page_entry = page_entries.get(page, {})
        conn.execute(
            """
            INSERT INTO pages (
              group_id, page_no, image_path, generation_hint_json, text_items_json, line_items_json,
              raw_markers_json, manual_notes_json, people_locked, page_role, keep_generation_axis
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, page_no) DO UPDATE SET
              image_path = excluded.image_path,
              generation_hint_json = excluded.generation_hint_json,
              text_items_json = excluded.text_items_json,
              line_items_json = excluded.line_items_json,
              raw_markers_json = excluded.raw_markers_json,
              manual_notes_json = excluded.manual_notes_json,
              people_locked = excluded.people_locked,
              page_role = excluded.page_role,
              keep_generation_axis = excluded.keep_generation_axis,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                payload["group_id"],
                page,
                page_entry.get("image"),
                json_text(page_entry.get("generation_hint", [])),
                json_text(page_entry.get("text_items", [])),
                json_text(page_entry.get("line_items", [])),
                json_text(page_entry.get("raw_markers", [])),
                json_text(page_entry.get("manual_notes", [])),
                1 if page_entry.get("people_locked") else 0,
                page_entry.get("page_role"),
                1 if page_entry.get("keep_generation_axis") else 0,
            ),
        )
    return page_entries


def insert_persons(conn: sqlite3.Connection, payload: dict[str, Any], glyph_dir: Path) -> None:
    pages_by_no = {item["page"]: item for item in payload.get("pages_data", [])}
    for person in payload.get("persons", []):
        primary_ref = pick_primary_ref(person)
        primary_page_no = primary_ref.get("page")
        page_entry = pages_by_no.get(primary_page_no or -1, {})
        glyph_asset_path = export_glyph(person["id"], person.get("glyph_image"), glyph_dir)
        conn.execute(
            """
            INSERT INTO persons (
              id, group_id, name, canonical_name, generation, root_order, primary_page_no,
              primary_page_image_path, bbox_json, poly_json, glyph_asset_path, aliases_json, notes_json,
              is_verified, verified_at, review_status, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              group_id = excluded.group_id,
              name = excluded.name,
              canonical_name = excluded.canonical_name,
              generation = excluded.generation,
              root_order = excluded.root_order,
              primary_page_no = excluded.primary_page_no,
              primary_page_image_path = excluded.primary_page_image_path,
              bbox_json = excluded.bbox_json,
              poly_json = excluded.poly_json,
              glyph_asset_path = excluded.glyph_asset_path,
              aliases_json = excluded.aliases_json,
              notes_json = excluded.notes_json,
              is_verified = excluded.is_verified,
              verified_at = excluded.verified_at,
              review_status = excluded.review_status,
              remark = excluded.remark,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                person["id"],
                payload["group_id"],
                person.get("name") or person["id"],
                person.get("name") or person["id"],
                int(person.get("generation") or 0),
                person.get("root_order"),
                primary_page_no,
                page_entry.get("image"),
                json_text(primary_ref.get("box")) if primary_ref.get("box") is not None else None,
                json_text(primary_ref.get("poly")) if primary_ref.get("poly") is not None else None,
                glyph_asset_path,
                json_text(person.get("aliases", [])),
                json_text(person.get("notes", [])),
                1 if person.get("is_verified") else 0,
                person.get("verified_at"),
                person.get("review_status") or "draft",
                person.get("remark"),
            ),
        )


def insert_relationships(conn: sqlite3.Connection, payload: dict[str, Any], *, scope: str, scope_ref: str) -> None:
    for edge in payload.get("edges", []):
        conn.execute(
            """
            INSERT INTO relationships (
              scope, scope_ref, parent_person_id, child_person_id, relation_type,
              birth_order_under_parent, confidence, page_sources_json, notes_json,
              is_verified, verified_at, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, scope_ref, parent_person_id, child_person_id, relation_type) DO UPDATE SET
              birth_order_under_parent = excluded.birth_order_under_parent,
              confidence = excluded.confidence,
              page_sources_json = excluded.page_sources_json,
              notes_json = excluded.notes_json,
              is_verified = excluded.is_verified,
              verified_at = excluded.verified_at,
              remark = excluded.remark,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                scope,
                scope_ref,
                edge["from_person_id"],
                edge["to_person_id"],
                edge.get("relation") or "father_child",
                edge.get("birth_order_under_parent"),
                edge.get("confidence"),
                json_text(edge.get("page_sources", [])),
                json_text(edge.get("notes", [])),
                1 if edge.get("is_verified") else 0,
                edge.get("verified_at"),
                edge.get("remark"),
            ),
        )


def import_group(conn: sqlite3.Connection, path: Path, glyph_dir: Path) -> None:
    payload = load_json(path)
    insert_group(conn, payload)
    insert_pages(conn, payload)
    insert_persons(conn, payload, glyph_dir)
    insert_relationships(conn, payload, scope="group_internal", scope_ref=payload["group_id"])


def import_bridge(conn: sqlite3.Connection, path: Path) -> None:
    payload = load_json(path)
    scope_ref = payload.get("workspace_id") or path.stem
    insert_relationships(conn, payload, scope="group_bridge", scope_ref=scope_ref)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import genealogy JSON workspaces into SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database output path.")
    parser.add_argument("--group-json", action="append", type=Path, dest="group_jsons", help="Path to a group_template.json.")
    parser.add_argument("--bridge-json", action="append", type=Path, dest="bridge_jsons", help="Path to a bridge json.")
    parser.add_argument("--glyph-dir", type=Path, default=ROOT / "data" / "glyph_assets", help="Directory to export glyph images into.")
    parser.add_argument("--reset", action="store_true", help="Delete the target db before importing.")
    return parser.parse_args()


def sync_workspace_to_sqlite(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    group_jsons: list[Path] | None = None,
    bridge_jsons: list[Path] | None = None,
    glyph_dir: Path = ROOT / "data" / "glyph_assets",
    reset: bool = True,
) -> Path:
    if reset and db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        create_schema(conn)
        for group_json in group_jsons or DEFAULT_GROUP_JSONS:
            import_group(conn, group_json, glyph_dir)
        for bridge_json in bridge_jsons or DEFAULT_BRIDGE_JSONS:
            if bridge_json.exists():
                import_bridge(conn, bridge_json)
        conn.commit()
    finally:
        conn.close()
    return db_path


def main() -> None:
    args = parse_args()
    db_path = sync_workspace_to_sqlite(
        db_path=args.db,
        group_jsons=args.group_jsons,
        bridge_jsons=args.bridge_jsons,
        glyph_dir=args.glyph_dir,
        reset=args.reset,
    )
    print(db_path)


if __name__ == "__main__":
    main()
