#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from import_genealogy_to_sqlite import DEFAULT_DB_PATH, sync_workspace_to_sqlite
from run_biography_review_server import (
    build_initial_state as build_bio_initial_state,
    load_json as load_bio_json,
    normalize_state as normalize_bio_state,
    sync_state_to_sqlite as sync_bio_state_to_sqlite,
)
from workspace_paths import ROOT

DEFAULT_GROUP_JSON = ROOT / "gen_093_097" / "group_template.json"
GROUP_JSON = DEFAULT_GROUP_JSON
MERGE_WORKSPACE_PREFIX = "merge__"
BRIDGE_DIR = ROOT / "bridges"
SQLITE_DB_PATH = DEFAULT_DB_PATH
GLYPH_ASSET_DIR = ROOT / "data" / "glyph_assets"
OCR_VENV_PYTHON = ROOT / ".venvs" / "paddleocr311" / "bin" / "python"
PERSON_OCR_HELPER = ROOT / "scripts" / "person_name_ocr_helper.py"
GENEALOGY_UI_DIR = ROOT / "frontend" / "genealogy-editor"
BIOGRAPHY_UI_DIR = ROOT / "frontend" / "biography-review"
PERSON_OPTIONAL_DETAIL_COLUMNS = [
    "source_columns_json",
    "source_text_raw",
    "source_text_linear",
    "source_text_punctuated",
    "source_text_baihua",
    "match_status",
]
BIO_PROJECT_DIRS: dict[str, Path] = {}
BIO_DEFAULT_PROJECT_ID: str | None = None
SQLITE_MIRROR_MIN_INTERVAL_SECONDS = 120
LAST_SQLITE_MIRROR_AT = 0.0


class ReviewHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def parse_group_range(group_id: str | None) -> tuple[int | None, int | None]:
    parts = str(group_id or "").split("_")
    if len(parts) != 3:
        return (None, None)
    try:
        return (int(parts[1]), int(parts[2]))
    except ValueError:
        return (None, None)


def use_db_mode_for_group(group_id: str | None) -> bool:
    if not group_id or parse_merge_workspace_id(group_id):
        return False
    start, end = parse_group_range(group_id)
    return start is not None and end is not None and end <= 102


def parse_merge_workspace_id(group_param: str | None) -> list[str] | None:
    if not group_param or not group_param.startswith(MERGE_WORKSPACE_PREFIX):
        return None
    parts = group_param[len(MERGE_WORKSPACE_PREFIX):].split("__")
    return [part for part in parts if part] or None


def resolve_group_json(group_param: str | None) -> Path:
    if parse_merge_workspace_id(group_param):
        return ROOT / (group_param or "merge_virtual") / "virtual.json"
    if group_param:
        candidate = ROOT / group_param / "group_template.json"
        if candidate.exists():
            return candidate
    return GROUP_JSON


def bridge_json_path(left_group_id: str, right_group_id: str) -> Path:
    return BRIDGE_DIR / f"{left_group_id}__{right_group_id}.json"


def ensure_bridge_payload(left_group_id: str, right_group_id: str) -> dict:
    path = bridge_json_path(left_group_id, right_group_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "workspace_id": f"{MERGE_WORKSPACE_PREFIX}{left_group_id}__{right_group_id}",
        "left_group_id": left_group_id,
        "right_group_id": right_group_id,
        "edges": [],
        "notes": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def incoming_children(edges: list[dict]) -> set[str]:
    return {edge["to_person_id"] for edge in edges}


def compute_group_completion(data: dict) -> dict:
    generations = [int(person.get("generation", 0)) for person in data.get("persons", []) if int(person.get("generation", 0) or 0) > 0]
    if not generations:
        return {"ready": False, "min_generation": None, "missing_people": []}
    min_generation = min(generations)
    incoming = incoming_children(data.get("edges", []))
    missing_people = []
    for person in data.get("persons", []):
        generation = int(person.get("generation", 0) or 0)
        if generation <= min_generation:
            continue
        if person.get("id") in incoming:
            continue
        refs = person.get("text_refs") or ([person["text_ref"]] if person.get("text_ref") else [])
        pages = sorted(int(ref.get("page")) for ref in refs if ref.get("page"))
        missing_people.append(
            {
                "person_id": person.get("id"),
                "name": person.get("name") or person.get("id"),
                "generation": generation,
                "page": pages[0] if pages else None,
            }
        )
    missing_people.sort(key=lambda item: (item.get("page") or 9999, item.get("generation") or 9999, item.get("name") or ""))
    return {
        "ready": len(missing_people) == 0,
        "min_generation": min_generation,
        "missing_people": missing_people,
    }


def label_for_group_range(group_ids: list[str]) -> str:
    starts = []
    ends = []
    for group_id in group_ids:
        parts = group_id.split("_")
        if len(parts) != 3:
            continue
        starts.append(int(parts[1]))
        ends.append(int(parts[2]))
    if not starts or not ends:
        return "合并衔接"
    return f"{min(starts)}-{max(ends)}世合并衔接"


def build_merge_workspace_payload(source_group_ids: list[str]) -> dict:
    groups = []
    for group_id in source_group_ids:
        payload = json.loads((ROOT / group_id / "group_template.json").read_text(encoding="utf-8"))
        payload["persons"] = [
            {
                **person,
                "source_group_id": group_id,
            }
            for person in payload.get("persons", [])
        ]
        groups.append(payload)

    pages = sorted({page for payload in groups for page in payload.get("pages", [])})
    page_entries = {}
    page_group_members = {}
    for payload in groups:
        group_id = payload["group_id"]
        for page_entry in payload.get("pages_data", []):
            page = page_entry["page"]
            page_group_members.setdefault(str(page), [])
            if group_id not in page_group_members[str(page)]:
                page_group_members[str(page)].append(group_id)
            if page not in page_entries:
                page_entries[page] = {**page_entry}
                continue
            merged_hint = sorted({
                *page_entries[page].get("generation_hint", []),
                *page_entry.get("generation_hint", []),
            })
            page_entries[page]["generation_hint"] = merged_hint

    bridge_edges = []
    for index in range(len(source_group_ids) - 1):
        left_group_id = source_group_ids[index]
        right_group_id = source_group_ids[index + 1]
        bridge = ensure_bridge_payload(left_group_id, right_group_id)
        bridge_edges.extend(bridge.get("edges", []))

    merged = {
        "group_id": f"{MERGE_WORKSPACE_PREFIX}{'__'.join(source_group_ids)}",
        "workspace_type": "merge",
        "label": label_for_group_range(source_group_ids),
        "source_groups": source_group_ids,
        "pages": pages,
        "persons": [person for payload in groups for person in payload.get("persons", [])],
        "edges": [edge for payload in groups for edge in payload.get("edges", [])] + bridge_edges,
        "pages_data": [page_entries[page] for page in pages],
        "page_group_members": page_group_members,
    }
    merged["generations"] = sorted({int(person.get("generation", 0)) for person in merged["persons"] if int(person.get("generation", 0) or 0) > 0})
    return merged


def payload_for_group(group_param: str | None) -> dict:
    merge_source_group_ids = parse_merge_workspace_id(group_param)
    if merge_source_group_ids:
        return sanitize_payload_glyph_images(build_merge_workspace_payload(merge_source_group_ids))
    if use_db_mode_for_group(group_param):
        return build_group_payload_from_db(group_param)
    payload = json.loads(resolve_group_json(group_param).read_text(encoding="utf-8"))
    payload["workspace_type"] = "group"
    payload["persons"] = [
        {
            **person,
            "source_group_id": payload["group_id"],
        }
        for person in payload.get("persons", [])
    ]
    if "generations" not in payload:
        payload["generations"] = sorted({int(person.get("generation", 0)) for person in payload.get("persons", []) if int(person.get("generation", 0) or 0) > 0})
    return sanitize_payload_glyph_images(payload)


def group_json_path(group_id: str) -> Path:
    return ROOT / group_id / "group_template.json"


def load_group_payload(group_id: str) -> dict:
    return json.loads(group_json_path(group_id).read_text(encoding="utf-8"))


def save_group_payload(group_id: str, payload: dict) -> Path:
    path = group_json_path(group_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_group_payload_from_db(group_id: str) -> dict:
    json_payload = load_group_payload(group_id)
    json_people = {person.get("id"): person for person in json_payload.get("persons", [])}
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        group_row = conn.execute(
            """
            SELECT id, label, source_pdf, raw_images_dir, cropped_images_dir
            FROM groups
            WHERE id = ?
            """,
            (group_id,),
        ).fetchone()
        if not group_row:
            raise KeyError(f"Group not found in sqlite: {group_id}")
        page_rows = conn.execute(
            """
            SELECT page_no, image_path, generation_hint_json, text_items_json, line_items_json,
                   raw_markers_json, manual_notes_json, people_locked, page_role, keep_generation_axis
            FROM pages
            WHERE group_id = ?
            ORDER BY page_no
            """,
            (group_id,),
        ).fetchall()
        person_rows = conn.execute(
            """
            SELECT id, name, generation, root_order, primary_page_no, primary_page_image_path,
                   bbox_json, poly_json, glyph_asset_path, aliases_json, notes_json,
                   is_verified, verified_at, review_status, remark
            FROM persons
            WHERE group_id = ?
            ORDER BY generation, primary_page_no, name
            """,
            (group_id,),
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT parent_person_id, child_person_id, relation_type, birth_order_under_parent,
                   confidence, page_sources_json, notes_json, is_verified, verified_at, remark
            FROM relationships
            WHERE scope = 'group_internal' AND scope_ref = ?
            ORDER BY parent_person_id, birth_order_under_parent, child_person_id
            """,
            (group_id,),
        ).fetchall()
    finally:
        conn.close()

    pages_data = []
    for row in page_rows:
        pages_data.append(
            {
                "page": row["page_no"],
                "image": row["image_path"],
                "generation_hint": json.loads(row["generation_hint_json"] or "[]"),
                "text_items": json.loads(row["text_items_json"] or "[]"),
                "line_items": json.loads(row["line_items_json"] or "[]"),
                "raw_markers": json.loads(row["raw_markers_json"] or "[]"),
                "manual_notes": json.loads(row["manual_notes_json"] or "[]"),
                "people_locked": bool(row["people_locked"]),
                "page_role": row["page_role"],
                "keep_generation_axis": bool(row["keep_generation_axis"]),
            }
        )

    persons = []
    for row in person_rows:
        json_person = json_people.get(row["id"], {})
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        poly = json.loads(row["poly_json"]) if row["poly_json"] else None
        text_refs = json_person.get("text_refs")
        text_ref = json_person.get("text_ref")
        if not text_refs and row["primary_page_no"] and bbox:
            text_ref = {
                "page": row["primary_page_no"],
                "index": row["id"],
                "text": row["name"],
                "box": bbox,
                "poly": poly,
            }
            text_refs = [text_ref]
        persons.append(
            {
                **json_person,
                "id": row["id"],
                "name": row["name"],
                "generation": row["generation"],
                "root_order": row["root_order"],
                "glyph_image": image_url_for_path(row["glyph_asset_path"]) or json_person.get("glyph_image") or "",
                "aliases": json.loads(row["aliases_json"] or "[]"),
                "notes": json.loads(row["notes_json"] or "[]"),
                "is_verified": bool(row["is_verified"]),
                "verified_at": row["verified_at"],
                "review_status": row["review_status"],
                "remark": row["remark"],
                "text_ref": text_ref,
                "text_refs": text_refs or ([] if text_ref is None else [text_ref]),
            }
        )

    edges = []
    for row in edge_rows:
        edges.append(
            {
                "from_person_id": row["parent_person_id"],
                "to_person_id": row["child_person_id"],
                "relation": row["relation_type"],
                "birth_order_under_parent": row["birth_order_under_parent"],
                "confidence": row["confidence"],
                "page_sources": json.loads(row["page_sources_json"] or "[]"),
                "notes": json.loads(row["notes_json"] or "[]"),
                "is_verified": bool(row["is_verified"]),
                "verified_at": row["verified_at"],
                "remark": row["remark"],
            }
        )

    payload = {
        "group_id": group_row["id"],
        "label": group_row["label"],
        "source_pdf": group_row["source_pdf"],
        "raw_images_dir": group_row["raw_images_dir"],
        "cropped_images_dir": group_row["cropped_images_dir"],
        "workspace_type": "group",
        "storage_mode": "sqlite",
        "pages": [row["page_no"] for row in page_rows],
        "pages_data": pages_data,
        "persons": persons,
        "edges": edges,
    }
    payload["generations"] = sorted(
        {int(person.get("generation", 0)) for person in persons if int(person.get("generation", 0) or 0) > 0}
    )
    return payload


def find_person_payload(group_id: str, person_id: str) -> tuple[dict, dict, dict]:
    payload = load_group_payload(group_id)
    person = next((item for item in payload.get("persons", []) if item.get("id") == person_id), None)
    if not person:
        raise KeyError(f"Person {person_id} not found in {group_id}")
    pages_by_no = {item.get("page"): item for item in payload.get("pages_data", [])}
    return payload, person, pages_by_no


def available_person_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(persons)").fetchall()}


def normalize_text_refs(person: dict) -> list[dict]:
    refs = []
    if isinstance(person.get("text_refs"), list):
        refs.extend([ref for ref in person["text_refs"] if isinstance(ref, dict)])
    if isinstance(person.get("text_ref"), dict):
        key = (person["text_ref"].get("page"), person["text_ref"].get("index"))
        if not any((ref.get("page"), ref.get("index")) == key for ref in refs):
            refs.insert(0, person["text_ref"])
    return refs


def image_url_for_path(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("/") else f"/{path.lstrip('/')}"


def glyph_asset_url_for_person_id(person_id: str | None) -> str:
    if not person_id:
        return ""
    for ext in ("png", "jpg", "jpeg", "webp"):
        candidate = GLYPH_ASSET_DIR / f"{person_id}.{ext}"
        if candidate.exists():
            return f"/data/glyph_assets/{candidate.name}"
    return ""


def sanitize_payload_glyph_images(payload: dict) -> dict:
    persons = payload.get("persons", [])
    if not isinstance(persons, list):
        return payload
    for person in persons:
        if not isinstance(person, dict):
            continue
        glyph_image = person.get("glyph_image")
        if isinstance(glyph_image, str) and glyph_image.startswith("data:image/"):
            person["glyph_image"] = glyph_asset_url_for_person_id(person.get("id")) or ""
    return payload


def build_person_detail_payload(person_id: str) -> dict:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        person_columns = available_person_columns(conn)
        optional_selects = []
        for column in PERSON_OPTIONAL_DETAIL_COLUMNS:
            if column in person_columns:
                optional_selects.append(f"p.{column}")
            else:
                optional_selects.append(f"bio.{column}")
        optional_sql = (",\n              " + ",\n              ".join(optional_selects)) if optional_selects else ""
        row = conn.execute(
            f"""
            SELECT
              p.id,
              p.group_id,
              p.name,
              p.canonical_name,
              p.generation,
              p.root_order,
              p.primary_page_no,
              p.primary_page_image_path,
              p.glyph_asset_path,
              p.bbox_json,
              p.poly_json,
              p.aliases_json,
              p.notes_json,
              p.is_verified,
              p.verified_at,
              p.review_status,
              p.remark,
              COALESCE(tree.tree_status, 'isolated') AS tree_status,
              COALESCE(tree.internal_parent_links, 0) AS internal_parent_links,
              COALESCE(tree.bridge_parent_links, 0) AS bridge_parent_links,
              COALESCE(tree.child_count, 0) AS child_count
              {optional_sql}
            FROM persons
            AS p
            LEFT JOIN v_person_tree_status AS tree
              ON tree.person_id = p.id
            LEFT JOIN (
              SELECT ranked.*
              FROM (
                SELECT
                  pb.*,
                  ROW_NUMBER() OVER (
                    PARTITION BY pb.person_id
                    ORDER BY
                      CASE pb.match_status
                        WHEN 'reviewed_manual' THEN 0
                        WHEN 'candidate_exact_unique' THEN 1
                        WHEN 'candidate_normalized_unique' THEN 2
                        ELSE 9
                      END,
                      pb.updated_at DESC,
                      pb.id DESC
                  ) AS row_rank
                FROM person_biographies AS pb
              ) AS ranked
              WHERE ranked.row_rank = 1
            ) AS bio
              ON bio.person_id = p.id
            WHERE p.id = ?
            """,
            (person_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": f"未找到人物 {person_id}"}

    payload, person, pages_by_no = find_person_payload(row["group_id"], person_id)
    refs = normalize_text_refs(person)
    page_details = []
    for page_no in sorted({int(ref.get("page")) for ref in refs if ref.get("page")}):
        page_entry = pages_by_no.get(page_no, {})
        page_refs = [ref for ref in refs if int(ref.get("page") or 0) == page_no]
        page_details.append(
            {
                "page": page_no,
                "image_path": image_url_for_path(page_entry.get("image") or row["primary_page_image_path"]),
                "refs": page_refs,
            }
        )

    return {
        "ok": True,
        "person": {
            "id": row["id"],
            "group_id": row["group_id"],
            "name": person.get("name") or row["name"],
            "canonical_name": row["canonical_name"],
            "generation": person.get("generation") or row["generation"],
            "root_order": person.get("root_order") or row["root_order"],
            "primary_page_no": row["primary_page_no"],
            "primary_page_image_path": image_url_for_path(row["primary_page_image_path"]),
            "glyph_image": image_url_for_path(row["glyph_asset_path"]) or person.get("glyph_image") or "",
            "text_ref": person.get("text_ref"),
            "text_refs": refs,
            "page_sources": person.get("page_sources", []),
            "aliases": json.loads(row["aliases_json"]) if row["aliases_json"] else person.get("aliases", []),
            "notes": json.loads(row["notes_json"]) if row["notes_json"] else person.get("notes", []),
            "bbox": json.loads(row["bbox_json"]) if row["bbox_json"] else None,
            "poly": json.loads(row["poly_json"]) if row["poly_json"] else None,
            "is_verified": bool(row["is_verified"]),
            "verified_at": row["verified_at"],
            "review_status": row["review_status"],
            "remark": row["remark"],
            "tree_status": row["tree_status"],
            "internal_parent_links": row["internal_parent_links"],
            "bridge_parent_links": row["bridge_parent_links"],
            "child_count": row["child_count"],
            "source_columns_json": row["source_columns_json"] if "source_columns_json" in row.keys() else None,
            "source_text_raw": row["source_text_raw"] if "source_text_raw" in row.keys() else None,
            "source_text_linear": row["source_text_linear"] if "source_text_linear" in row.keys() else None,
            "source_text_punctuated": row["source_text_punctuated"] if "source_text_punctuated" in row.keys() else None,
            "source_text_baihua": row["source_text_baihua"] if "source_text_baihua" in row.keys() else None,
            "match_status": row["match_status"] if "match_status" in row.keys() else None,
        },
        "pages": page_details,
    }


def update_person_name_payload(person_id: str, new_name: str) -> dict:
    cleaned_name = str(new_name or "").strip()
    if not cleaned_name:
        return {"ok": False, "error": "姓名不能为空"}
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT group_id FROM persons WHERE id = ?", (person_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": f"未找到人物 {person_id}"}

    payload, person, _ = find_person_payload(row["group_id"], person_id)
    person["name"] = cleaned_name
    if isinstance(person.get("text_ref"), dict):
        person["text_ref"]["text"] = cleaned_name
    if isinstance(person.get("text_refs"), list):
        for ref in person["text_refs"]:
            if isinstance(ref, dict):
                ref["text"] = cleaned_name
    notes = [str(item) for item in person.get("notes", [])]
    if "人工更正姓名" not in notes:
        notes.append("人工更正姓名")
    person["notes"] = notes
    path = save_group_payload(row["group_id"], payload)
    mirror = sync_sqlite_mirror()
    detail = build_person_detail_payload(person_id)
    return {"ok": True, "path": str(path), "sqlite_mirror": mirror, "detail": detail}


def crop_person_glyph(person_id: str) -> dict:
    detail = build_person_detail_payload(person_id)
    if not detail.get("ok"):
        return detail
    person = detail["person"]
    glyph_image_path = person.get("glyph_image")
    if glyph_image_path:
        local_glyph_path = ROOT / str(glyph_image_path).lstrip("/")
        if local_glyph_path.exists():
            return {
                "ok": True,
                "crop_box": None,
                "ocr_source_path": str(local_glyph_path),
                "detail": detail,
            }
    ref = person.get("text_ref") or (person.get("text_refs") or [None])[0]
    if not isinstance(ref, dict) or not ref.get("box"):
        return {"ok": False, "error": "该人物没有可用的文字框，无法重做 OCR"}
    page_image_path = person.get("primary_page_image_path")
    if not page_image_path:
        return {"ok": False, "error": "该人物没有整页图路径"}

    image_path = ROOT / str(page_image_path).lstrip("/")
    if not image_path.exists():
        return {"ok": False, "error": f"整页图不存在：{image_path}"}
    return {
        "ok": True,
        "crop_box": ref["box"],
        "detail": detail,
        "ocr_source_path": str(image_path),
    }


def rerun_person_ocr_payload(person_id: str) -> dict:
    cropped = crop_person_glyph(person_id)
    if not cropped.get("ok"):
        return cropped
    if not OCR_VENV_PYTHON.exists():
        return {"ok": False, "error": f"未找到 OCR 虚拟环境：{OCR_VENV_PYTHON}"}
    if not PERSON_OCR_HELPER.exists():
        return {"ok": False, "error": f"未找到 OCR helper：{PERSON_OCR_HELPER}"}
    command = [str(OCR_VENV_PYTHON), str(PERSON_OCR_HELPER), "--image", cropped["ocr_source_path"]]
    if cropped.get("crop_box"):
        command.extend(["--box", json.dumps(cropped["crop_box"], ensure_ascii=False)])
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"},
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": (completed.stderr or completed.stdout or "PaddleOCR 执行失败").strip(),
        }
    payload = json.loads(completed.stdout)
    candidates = payload.get("candidates") or []
    return {
        "ok": True,
        "person_id": person_id,
        "crop_image": payload.get("crop_image", ""),
        "lines": payload.get("lines", []),
        "candidates": candidates,
        "detail": cropped["detail"],
    }


def current_sqlite_mirror_summary() -> dict:
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        try:
            group_count = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            person_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
            relationship_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        finally:
            conn.close()
        return {
            "ok": True,
            "db_path": str(SQLITE_DB_PATH),
            "group_count": group_count,
            "person_count": person_count,
            "relationship_count": relationship_count,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "db_path": str(SQLITE_DB_PATH)}


def sync_sqlite_mirror(force: bool = True) -> dict:
    global LAST_SQLITE_MIRROR_AT
    now = time.time()
    if not force and now - LAST_SQLITE_MIRROR_AT < SQLITE_MIRROR_MIN_INTERVAL_SECONDS:
        summary = current_sqlite_mirror_summary()
        summary["skipped"] = True
        summary["reason"] = "throttled"
        return summary
    try:
        db_path = sync_workspace_to_sqlite(db_path=SQLITE_DB_PATH, reset=True)
        LAST_SQLITE_MIRROR_AT = now
        summary = current_sqlite_mirror_summary()
        summary["db_path"] = str(db_path)
        return summary
    except Exception as exc:  # pragma: no cover - defensive path for local tool
        return {"ok": False, "error": str(exc), "db_path": str(SQLITE_DB_PATH)}


def person_lookup_rows(person_id: str | None, name: str | None) -> list[dict]:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        clauses = []
        params = []
        if person_id:
            clauses.append("id = ?")
            params.append(person_id)
        if name:
            clauses.append("(name LIKE ? OR canonical_name LIKE ?)")
            params.extend([f"%{name}%", f"%{name}%"])
        if not clauses:
            return []
        rows = conn.execute(
            f"""
            SELECT id, group_id, name, generation, primary_page_no
            FROM persons
            WHERE {' AND '.join(clauses)}
            ORDER BY generation, primary_page_no, name
            LIMIT 20
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_tree_payload(person_id: str | None, name: str | None, direction: str, depth: int | None) -> dict:
    matches = person_lookup_rows(person_id, name)
    if not matches:
        return {
            "ok": True,
            "query": {"person_id": person_id, "name": name, "direction": direction, "depth": depth},
            "matched_persons": [],
            "ancestors": [],
            "descendants": [],
        }
    target_id = person_id or matches[0]["id"]
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        target = conn.execute(
            """
            SELECT id, group_id, name, generation, primary_page_no, primary_page_image_path
            FROM persons
            WHERE id = ?
            """,
            (target_id,),
        ).fetchone()
        ancestors = []
        descendants = []
        max_depth = depth if depth and depth > 0 else 999
        if direction in ("up", "both"):
            ancestors = [
                dict(row)
                for row in conn.execute(
                    """
                    WITH RECURSIVE ancestor_chain(level, person_id, group_id, name, generation, primary_page_no, via_scope, via_scope_ref, from_person_id) AS (
                      SELECT
                        1 AS level,
                        p.id,
                        p.group_id,
                        p.name,
                        p.generation,
                        p.primary_page_no,
                        r.scope,
                        r.scope_ref,
                        r.parent_person_id
                      FROM relationships AS r
                      JOIN persons AS p
                        ON p.id = r.parent_person_id
                      WHERE r.child_person_id = ?
                      UNION ALL
                      SELECT
                        ancestor_chain.level + 1,
                        p.id,
                        p.group_id,
                        p.name,
                        p.generation,
                        p.primary_page_no,
                        r.scope,
                        r.scope_ref,
                        r.parent_person_id
                      FROM ancestor_chain
                      JOIN relationships AS r
                        ON r.child_person_id = ancestor_chain.person_id
                      JOIN persons AS p
                        ON p.id = r.parent_person_id
                      WHERE ancestor_chain.level < ?
                    )
                    SELECT *
                    FROM ancestor_chain
                    ORDER BY level, generation, primary_page_no, name
                    """,
                    (target_id, max_depth),
                ).fetchall()
            ]
        if direction in ("down", "both"):
            descendants = [
                dict(row)
                for row in conn.execute(
                    """
                    WITH RECURSIVE descendant_chain(level, person_id, group_id, name, generation, primary_page_no, via_scope, via_scope_ref, to_person_id) AS (
                      SELECT
                        1 AS level,
                        p.id,
                        p.group_id,
                        p.name,
                        p.generation,
                        p.primary_page_no,
                        r.scope,
                        r.scope_ref,
                        r.child_person_id
                      FROM relationships AS r
                      JOIN persons AS p
                        ON p.id = r.child_person_id
                      WHERE r.parent_person_id = ?
                      UNION ALL
                      SELECT
                        descendant_chain.level + 1,
                        p.id,
                        p.group_id,
                        p.name,
                        p.generation,
                        p.primary_page_no,
                        r.scope,
                        r.scope_ref,
                        r.child_person_id
                      FROM descendant_chain
                      JOIN relationships AS r
                        ON r.parent_person_id = descendant_chain.person_id
                      JOIN persons AS p
                        ON p.id = r.child_person_id
                      WHERE descendant_chain.level < ?
                    )
                    SELECT *
                    FROM descendant_chain
                    ORDER BY level, generation, primary_page_no, name
                    """,
                    (target_id, max_depth),
                ).fetchall()
            ]
        return {
            "ok": True,
            "query": {"person_id": person_id, "name": name, "direction": direction, "depth": depth},
            "matched_persons": matches,
            "target_person": dict(target) if target else None,
            "ancestors": ancestors,
            "descendants": descendants,
        }
    finally:
        conn.close()


def query_summary_payload() -> dict:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    try:
        group_count = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        person_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        relationship_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        bridge_relationship_count = conn.execute(
            "SELECT COUNT(*) FROM relationships WHERE scope = 'group_bridge'"
        ).fetchone()[0]
        bridge_scope_count = conn.execute(
            "SELECT COUNT(DISTINCT scope_ref) FROM relationships WHERE scope = 'group_bridge'"
        ).fetchone()[0]
        range_missing_parent_count = conn.execute(
            """
            SELECT COALESCE(SUM(missing_parent_count), 0)
            FROM v_group_completion
            WHERE group_id != 'gen_103_107'
            """
        ).fetchone()[0]
        return {
            "ok": True,
            "group_count": group_count,
            "person_count": person_count,
            "relationship_count": relationship_count,
            "bridge_relationship_count": bridge_relationship_count,
            "bridge_scope_count": bridge_scope_count,
            "range_missing_parent_count": range_missing_parent_count,
            "range_ready": range_missing_parent_count == 0,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


def query_full_tree_payload(max_generation: int = 102) -> dict:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        people = [
            {
                "id": row["id"],
                "name": row["name"],
                "generation": row["generation"],
                "root_order": row["root_order"],
                "primary_page_no": row["primary_page_no"],
                "glyph_image": f"/{row['glyph_asset_path']}" if row["glyph_asset_path"] else "",
                "text_ref": {"page": row["primary_page_no"], "index": row["id"]} if row["primary_page_no"] else None,
                "source_group_id": row["group_id"],
            }
            for row in conn.execute(
                """
                SELECT id, group_id, name, generation, root_order, primary_page_no, glyph_asset_path
                FROM persons
                WHERE generation <= ?
                ORDER BY generation, primary_page_no, name
                """,
                (max_generation,),
            ).fetchall()
        ]
        edges = [
            {
                "from_person_id": row["parent_person_id"],
                "to_person_id": row["child_person_id"],
                "birth_order_under_parent": row["birth_order_under_parent"],
                "relation": row["relation_type"],
                "scope": row["scope"],
                "scope_ref": row["scope_ref"],
            }
            for row in conn.execute(
                """
                SELECT
                  r.parent_person_id,
                  r.child_person_id,
                  r.birth_order_under_parent,
                  r.relation_type,
                  r.scope,
                  r.scope_ref
                FROM relationships AS r
                JOIN persons AS p1
                  ON p1.id = r.parent_person_id
                JOIN persons AS p2
                  ON p2.id = r.child_person_id
                WHERE p1.generation <= ?
                  AND p2.generation <= ?
                ORDER BY p1.generation, p2.generation, r.scope, r.scope_ref, r.id
                """,
                (max_generation, max_generation),
            ).fetchall()
        ]
        pages = sorted({person["primary_page_no"] for person in people if person["primary_page_no"]})
        generations = sorted({person["generation"] for person in people if person["generation"]})
        return {
            "ok": True,
            "label": f"1-{max_generation}世完整树",
            "max_generation": max_generation,
            "pages": pages,
            "generations": generations,
            "persons": people,
            "edges": edges,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


def resolve_bio_project_dir(project_id: str | None) -> Path:
    effective_project_id = project_id or BIO_DEFAULT_PROJECT_ID
    project_dir = BIO_PROJECT_DIRS.get(str(effective_project_id or ""))
    if project_dir is None:
        raise KeyError(f"Unknown biography project: {effective_project_id}")
    return project_dir


def ensure_bio_state(project_id: str | None = None) -> Path:
    project_dir = resolve_bio_project_dir(project_id)
    review_dir = project_dir / "review"
    bundle_path = review_dir / "review_data.json"
    state_path = review_dir / "review_state.json"
    bundle = load_bio_json(bundle_path, {})
    if not state_path.exists():
        state_path.write_text(
            json.dumps(build_bio_initial_state(bundle), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return state_path


def bio_project_meta_list() -> list[dict]:
    rows = []
    for project_id, project_dir in sorted(BIO_PROJECT_DIRS.items()):
        project = load_bio_json(project_dir / "project.json", {})
        rows.append(
            {
                "project_id": project_id,
                "label": project.get("label") or project_id,
                "page_range": project.get("page_range") or [],
                "source_pdf": Path(project.get("source_pdf") or "").name or None,
            }
        )
    return rows


def bio_bundle_for_client(project_id: str) -> dict:
    project_dir = resolve_bio_project_dir(project_id)
    bundle_path = project_dir / "review" / "review_data.json"
    bundle = load_bio_json(bundle_path, {})
    pages = []
    for page in bundle.get("pages", []):
        page_copy = dict(page)
        for key in ("raw_image", "annotated_image", "ocr_json", "ocr_txt"):
            value = page_copy.get(key)
            if value and not str(value).startswith("/"):
                page_copy[key] = f"/{project_id}/{str(value).lstrip('/')}"
        pages.append(page_copy)
    bundle["pages"] = pages
    bundle["project_id"] = project_id
    return bundle


class ReviewHandler(SimpleHTTPRequestHandler):
    def address_string(self) -> str:
        return self.client_address[0]

    def end_headers(self) -> None:
        request_path = getattr(self, "path", "")
        parsed_path = urlparse(request_path).path if request_path else ""
        if parsed_path == "/review" or parsed_path.startswith("/review/"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        path = urlparse(path).path
        if path in {"/review", "/review/"}:
            return str((BIOGRAPHY_UI_DIR / "index.html").resolve())
        if path.startswith("/review/"):
            relative = path[len("/review/") :]
            return str((BIOGRAPHY_UI_DIR / relative).resolve())
        if path == "/":
            path = "/gen_093_097/editor/index.html"
        if path.startswith("/gen_093_097/editor/"):
            relative = path[len("/gen_093_097/editor/") :]
            return str((GENEALOGY_UI_DIR / relative).resolve())
        return str(ROOT / path.lstrip("/"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/review":
            self.send_response(301)
            self.send_header("Location", "/review/")
            self.end_headers()
            return
        if parsed.path == "/api/review-data":
            query = parse_qs(parsed.query)
            project_id = query.get("project_id", [BIO_DEFAULT_PROJECT_ID])[0]
            try:
                project_dir = resolve_bio_project_dir(project_id)
            except KeyError:
                body = json.dumps({"error": "unknown_project"}, ensure_ascii=False).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            state_path = ensure_bio_state(project_id)
            bundle = bio_bundle_for_client(str(project_id))
            state = load_bio_json(state_path, {})
            body = json.dumps(
                {
                    "bundle": bundle,
                    "state": state,
                    "projects": bio_project_meta_list(),
                    "selected_project_id": project_id,
                    "project_dir": str(project_dir),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/person-detail":
            query = parse_qs(parsed.query)
            person_id = query.get("person_id", [None])[0]
            payload = build_person_detail_payload(person_id) if person_id else {"ok": False, "error": "缺少 person_id"}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if payload.get("ok") else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/group":
            group_param = parse_qs(parsed.query).get("group", [None])[0]
            payload = payload_for_group(group_param)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/tree":
            query = parse_qs(parsed.query)
            person_id = query.get("person_id", [None])[0]
            name = query.get("name", [None])[0]
            direction = query.get("direction", ["both"])[0]
            if direction not in {"up", "down", "both"}:
                direction = "both"
            depth_raw = query.get("depth", [None])[0]
            depth = int(depth_raw) if depth_raw and str(depth_raw).isdigit() else None
            payload = query_tree_payload(person_id, name, direction, depth)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/summary":
            payload = query_summary_payload()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/full-tree":
            query = parse_qs(parsed.query)
            max_generation_raw = query.get("max_generation", ["102"])[0]
            max_generation = int(max_generation_raw) if str(max_generation_raw).isdigit() else 102
            payload = query_full_tree_payload(max_generation=max_generation)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/save-state":
            query = parse_qs(parsed.query)
            project_id = query.get("project_id", [None])[0]
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            effective_project_id = project_id or payload.get("project_id") or BIO_DEFAULT_PROJECT_ID
            try:
                project_dir = resolve_bio_project_dir(effective_project_id)
            except KeyError:
                body = json.dumps({"error": "unknown_project"}, ensure_ascii=False).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            bundle_path = project_dir / "review" / "review_data.json"
            state_path = ensure_bio_state(effective_project_id)
            bundle = load_bio_json(bundle_path, {})
            normalized = normalize_bio_state(bundle, payload, project_dir)
            state_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            sync_bio_state_to_sqlite(bundle, normalized, project_dir)
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/person-update":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            payload = update_person_name_payload(data.get("person_id"), data.get("name"))
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if payload.get("ok") else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/person-ocr":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            try:
                payload = rerun_person_ocr_payload(data.get("person_id"))
            except Exception as exc:  # pragma: no cover - local OCR dependency path
                payload = {"ok": False, "error": str(exc)}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if payload.get("ok") else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path != "/api/group":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        group_param = parse_qs(parsed.query).get("group", [None])[0]
        is_autosave = parse_qs(parsed.query).get("autosave", ["0"])[0] == "1"
        merge_source_group_ids = parse_merge_workspace_id(group_param)
        if merge_source_group_ids:
            group_people = {}
            for group_id in merge_source_group_ids:
                payload = json.loads((ROOT / group_id / "group_template.json").read_text(encoding="utf-8"))
                group_people[group_id] = {person["id"] for person in payload.get("persons", [])}
            saved_paths = []
            for index in range(len(merge_source_group_ids) - 1):
                left_group_id = merge_source_group_ids[index]
                right_group_id = merge_source_group_ids[index + 1]
                left_ids = group_people[left_group_id]
                right_ids = group_people[right_group_id]
                bridge_edges = [
                    edge
                    for edge in data.get("edges", [])
                    if (edge.get("from_person_id") in left_ids and edge.get("to_person_id") in right_ids)
                    or (edge.get("from_person_id") in right_ids and edge.get("to_person_id") in left_ids)
                ]
                payload = ensure_bridge_payload(left_group_id, right_group_id)
                payload["edges"] = bridge_edges
                path = bridge_json_path(left_group_id, right_group_id)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                saved_paths.append(str(path))
            mirror = sync_sqlite_mirror(force=not is_autosave)
            body = json.dumps({"ok": True, "paths": saved_paths, "sqlite_mirror": mirror}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        target_json = resolve_group_json(group_param)
        target_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mirror = sync_sqlite_mirror(force=not is_autosave)
        body = json.dumps({"ok": True, "path": str(target_json), "sqlite_mirror": mirror}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the genealogy review app for a selected group json.")
    parser.add_argument("--group-json", type=Path, default=DEFAULT_GROUP_JSON, help="Path to group_template.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> int:
    global GROUP_JSON, BIO_PROJECT_DIRS, BIO_DEFAULT_PROJECT_ID
    args = build_parser().parse_args()
    GROUP_JSON = args.group_json.resolve()
    BIO_PROJECT_DIRS = {
        path.name: path.resolve()
        for path in sorted(ROOT.glob("bio_*"))
        if (path / "project.json").exists() and (path / "review" / "review_data.json").exists()
    }
    BIO_DEFAULT_PROJECT_ID = sorted(BIO_PROJECT_DIRS.keys())[0] if BIO_PROJECT_DIRS else None
    for project_id in BIO_PROJECT_DIRS:
        ensure_bio_state(project_id)
    try:
        server = ReviewHTTPServer((args.host, args.port), ReviewHandler)
    except OSError as exc:
        print(f"Failed to bind review server at http://{args.host}:{args.port}: {exc}")
        return 1
    print(f"Serving review app at http://{args.host}:{args.port}")
    print(f"Using group data: {GROUP_JSON}")
    if BIO_DEFAULT_PROJECT_ID:
        print(f"Serving biography review at http://{args.host}:{args.port}/review/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
