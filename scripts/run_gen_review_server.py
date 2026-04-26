#!/usr/bin/env python3

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import subprocess
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from import_genealogy_to_sqlite import DEFAULT_DB_PATH, sync_group_payload_to_sqlite, sync_workspace_to_sqlite
from run_biography_review_server import (
    build_state_from_sqlite as build_bio_state_from_sqlite,
    load_json as load_bio_json,
    normalize_state as normalize_bio_state,
    sync_state_to_sqlite as sync_bio_state_to_sqlite,
)
from workspace_paths import (
    ROOT,
    WORKSPACE_BRIDGES_ROOT,
    WORKSPACE_GLYPH_ASSETS_ROOT,
    group_json_path as workspace_group_json_path,
    iter_bio_project_dirs,
    iter_group_dirs,
    resolve_repo_asset_path,
)

DEFAULT_GROUP_JSON = workspace_group_json_path("gen_093_097")
GROUP_JSON = DEFAULT_GROUP_JSON
MERGE_WORKSPACE_PREFIX = "merge__"
BRIDGE_DIR = WORKSPACE_BRIDGES_ROOT if WORKSPACE_BRIDGES_ROOT.exists() else ROOT / "bridges"
SQLITE_DB_PATH = DEFAULT_DB_PATH
GLYPH_ASSET_DIR = WORKSPACE_GLYPH_ASSETS_ROOT if WORKSPACE_GLYPH_ASSETS_ROOT.exists() else ROOT / "data" / "glyph_assets"
OCR_VENV_PYTHON = ROOT / ".venvs" / "paddleocr311" / "bin" / "python"
PERSON_OCR_HELPER = ROOT / "scripts" / "person_name_ocr_helper.py"
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
COMPLETE_TREE_MAX_GENERATION = 112
GEN_EDITOR_UI_DIR = ROOT / "products" / "genealogy-editor"
BIO_REVIEW_UI_DIR = ROOT / "products" / "biography-review"


def path_is_readable(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        if path.is_dir():
            next(path.iterdir(), None)
            return True
        path.read_bytes()
        return True
    except OSError:
        return False


def bio_project_accessible(project_dir: Path) -> bool:
    return (
        path_is_readable(project_dir)
        and path_is_readable(project_dir / "project.json")
        and path_is_readable(project_dir / "review" / "review_data.json")
    )


def parse_group_range(group_id: str | None) -> tuple[int | None, int | None]:
    parts = str(group_id or "").split("_")
    if len(parts) != 3:
        return (None, None)
    try:
        return (int(parts[1]), int(parts[2]))
    except ValueError:
        return (None, None)


def group_within_complete_tree(path: Path, *, max_generation: int = COMPLETE_TREE_MAX_GENERATION) -> bool:
    _, end_generation = parse_group_range(path.parent.name)
    return end_generation is not None and end_generation <= max_generation


def bridge_within_complete_tree(path: Path, *, max_generation: int = COMPLETE_TREE_MAX_GENERATION) -> bool:
    stem = path.stem
    if "__" not in stem:
        return False
    left_group_id, right_group_id = stem.split("__", 1)
    _, left_end = parse_group_range(left_group_id)
    _, right_end = parse_group_range(right_group_id)
    return (
        left_end is not None
        and right_end is not None
        and left_end <= max_generation
        and right_end <= max_generation
    )


def use_db_mode_for_group(group_id: str | None) -> bool:
    if not group_id or parse_merge_workspace_id(group_id):
        return False
    start, end = parse_group_range(group_id)
    return start is not None and end is not None


def parse_merge_workspace_id(group_param: str | None) -> list[str] | None:
    if not group_param or not group_param.startswith(MERGE_WORKSPACE_PREFIX):
        return None
    parts = group_param[len(MERGE_WORKSPACE_PREFIX):].split("__")
    return [part for part in parts if part] or None


def resolve_group_json(group_param: str | None) -> Path:
    if parse_merge_workspace_id(group_param):
        return ROOT / (group_param or "merge_virtual") / "virtual.json"
    if group_param:
        candidate = workspace_group_json_path(group_param)
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


def bridge_scope_ref(left_group_id: str, right_group_id: str) -> str:
    return f"{MERGE_WORKSPACE_PREFIX}{left_group_id}__{right_group_id}"


def upsert_bridge_payload_to_sqlite(payload: dict) -> dict:
    left_group_id = str(payload.get("left_group_id") or "").strip()
    right_group_id = str(payload.get("right_group_id") or "").strip()
    if not left_group_id or not right_group_id:
        return {"ok": False, "error": "bridge payload missing group ids", "edge_count": 0}
    edges = []
    for edge in payload.get("edges", []):
        if not isinstance(edge, dict):
            continue
        normalized = dict(edge)
        normalized["from_source_group_id"] = left_group_id
        normalized["to_source_group_id"] = right_group_id
        edges.append(normalized)
    edge_count = upsert_bridge_edges_to_sqlite(left_group_id, right_group_id, edges)
    return {
        "ok": True,
        "pair": f"{left_group_id}__{right_group_id}",
        "scope_ref": bridge_scope_ref(left_group_id, right_group_id),
        "edge_count": edge_count,
    }


def restore_related_bridges_to_sqlite(group_id: str | None) -> list[dict]:
    if not group_id:
        return []
    stats = []
    for path in sorted(BRIDGE_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            stats.append({"ok": False, "path": str(path), "error": str(exc), "edge_count": 0})
            continue
        left_group_id = str(payload.get("left_group_id") or "").strip()
        right_group_id = str(payload.get("right_group_id") or "").strip()
        if group_id not in {left_group_id, right_group_id}:
            continue
        stat = upsert_bridge_payload_to_sqlite(payload)
        stat["path"] = str(path)
        stats.append(stat)
    return stats


def upsert_bridge_edges_to_sqlite(left_group_id: str, right_group_id: str, edges: list[dict]) -> int:
    scope_ref = bridge_scope_ref(left_group_id, right_group_id)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    inserted = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            DELETE FROM relationships
            WHERE scope = 'group_bridge'
              AND EXISTS (
                SELECT 1
                FROM persons AS p1, persons AS p2
                WHERE p1.id = relationships.parent_person_id
                  AND p2.id = relationships.child_person_id
                  AND (
                    (p1.group_id = ? AND p2.group_id = ?)
                    OR (p1.group_id = ? AND p2.group_id = ?)
                  )
              )
            """,
            (left_group_id, right_group_id, right_group_id, left_group_id),
        )
        for edge in edges:
            parent_group = str(edge.get("from_source_group_id") or "")
            child_group = str(edge.get("to_source_group_id") or "")
            parent_source = str(edge.get("from_person_id") or "")
            child_source = str(edge.get("to_person_id") or "")
            if not parent_group or not child_group or not parent_source or not child_source:
                continue
            parent_id = f"{parent_group}::{parent_source}"
            child_id = f"{child_group}::{child_source}"
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
                    "group_bridge",
                    scope_ref,
                    parent_id,
                    child_id,
                    edge.get("relation") or "father_child",
                    edge.get("birth_order_under_parent"),
                    edge.get("confidence"),
                    json.dumps(edge.get("page_sources") or [], ensure_ascii=False),
                    json.dumps(edge.get("notes") or [], ensure_ascii=False),
                    1 if edge.get("is_verified") else 0,
                    edge.get("verified_at"),
                    edge.get("remark"),
                ),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def load_bridge_edges_from_sqlite(left_group_id: str, right_group_id: str) -> list[dict]:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              p1.group_id AS parent_group_id,
              p1.source_person_id AS parent_source_person_id,
              p2.group_id AS child_group_id,
              p2.source_person_id AS child_source_person_id,
              r.relation_type, r.birth_order_under_parent, r.confidence,
              r.page_sources_json, r.notes_json, r.is_verified, r.verified_at, r.remark
            FROM relationships AS r
            JOIN persons AS p1
              ON p1.id = r.parent_person_id
            JOIN persons AS p2
              ON p2.id = r.child_person_id
            WHERE r.scope = 'group_bridge'
              AND (
                (p1.group_id = ? AND p2.group_id = ?)
                OR (p1.group_id = ? AND p2.group_id = ?)
              )
            ORDER BY p1.source_person_id, p2.source_person_id
            """,
            (left_group_id, right_group_id, right_group_id, left_group_id),
        ).fetchall()
    finally:
        conn.close()

    edges: list[dict] = []
    for row in rows:
        edges.append(
            {
                "from_person_id": row["parent_source_person_id"],
                "to_person_id": row["child_source_person_id"],
                "relation": row["relation_type"] or "father_child",
                "birth_order_under_parent": row["birth_order_under_parent"],
                "confidence": row["confidence"],
                "page_sources": json.loads(row["page_sources_json"] or "[]"),
                "notes": json.loads(row["notes_json"] or "[]"),
                "is_verified": bool(row["is_verified"]),
                "verified_at": row["verified_at"],
                "remark": row["remark"],
                "from_source_group_id": row["parent_group_id"],
                "to_source_group_id": row["child_group_id"],
            }
        )
    return edges


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


def label_for_group_id(group_id: str) -> str:
    start, end = parse_group_range(group_id)
    if start is None or end is None:
        return group_id
    return f"{start}-{end}世"


def remap_ref_page_value(ref: dict, page_remap: dict[int, int]) -> dict:
    copied = dict(ref)
    page = copied.get("page")
    if isinstance(page, int) and page in page_remap:
        copied["page"] = page_remap[page]
    return copied


def merge_workspace_person_id(source_group_id: str, source_person_id: str) -> str:
    return f"{source_group_id}::{source_person_id}"


def remap_person_pages(
    person: dict,
    page_remap: dict[int, int],
    source_group_id: str,
    *,
    merged_person_id: str,
    source_person_id: str,
) -> dict:
    mapped = dict(person)
    mapped["id"] = merged_person_id
    mapped["source_person_id"] = source_person_id
    mapped["source_group_id"] = source_group_id
    if isinstance(mapped.get("text_ref"), dict):
        mapped["text_ref"] = remap_ref_page_value(mapped["text_ref"], page_remap)
        if mapped["text_ref"].get("index") == source_person_id:
            mapped["text_ref"]["index"] = merged_person_id
    if isinstance(mapped.get("text_refs"), list):
        converted_refs = []
        for ref in mapped["text_refs"]:
            if not isinstance(ref, dict):
                continue
            copied_ref = remap_ref_page_value(ref, page_remap)
            if copied_ref.get("index") == source_person_id:
                copied_ref["index"] = merged_person_id
            converted_refs.append(copied_ref)
        mapped["text_refs"] = converted_refs
    if isinstance(mapped.get("position_hints"), list):
        hints = []
        for hint in mapped["position_hints"]:
            if not isinstance(hint, dict):
                continue
            copied_hint = dict(hint)
            page = copied_hint.get("page")
            if isinstance(page, int) and page in page_remap:
                copied_hint["page"] = page_remap[page]
            hints.append(copied_hint)
        mapped["position_hints"] = hints
    if isinstance(mapped.get("page_sources"), list):
        mapped["page_sources"] = [page_remap.get(page, page) if isinstance(page, int) else page for page in mapped["page_sources"]]
    return mapped


def remap_edge_pages_and_ids(
    edge: dict,
    page_remap: dict[int, int],
    *,
    from_person_id: str,
    to_person_id: str,
) -> dict:
    mapped = dict(edge)
    mapped["from_person_id"] = from_person_id
    mapped["to_person_id"] = to_person_id
    if isinstance(mapped.get("page_sources"), list):
        mapped["page_sources"] = [page_remap.get(page, page) if isinstance(page, int) else page for page in mapped["page_sources"]]
    return mapped


def nearest_page_value(target_pages: list[int], value: int) -> int:
    if not target_pages:
        return value
    idx = bisect.bisect_left(target_pages, value)
    if idx <= 0:
        return target_pages[0]
    if idx >= len(target_pages):
        return target_pages[-1]
    left = target_pages[idx - 1]
    right = target_pages[idx]
    return left if abs(value - left) <= abs(value - right) else right


def build_page_linear_remap(source_pages: list[int], target_pages: list[int]) -> dict[int, int]:
    if not source_pages:
        return {}
    if not target_pages:
        return {page: page for page in source_pages}
    src = sorted({int(page) for page in source_pages})
    tgt = sorted({int(page) for page in target_pages})
    src_min, src_max = src[0], src[-1]
    tgt_min, tgt_max = tgt[0], tgt[-1]
    if src_min == src_max:
        mapped_page = nearest_page_value(tgt, tgt_min)
        return {page: mapped_page for page in src}
    remap: dict[int, int] = {}
    for page in src:
        ratio = (page - src_min) / (src_max - src_min)
        projected = int(round(tgt_min + ratio * (tgt_max - tgt_min)))
        remap[page] = nearest_page_value(tgt, projected)
    return remap


def build_merge_workspace_payload(source_group_ids: list[str]) -> dict:
    groups = []
    for group_id in source_group_ids:
        payload = json.loads(workspace_group_json_path(group_id).read_text(encoding="utf-8"))
        groups.append(payload)

    anchor_group = groups[-1]
    anchor_group_id = anchor_group["group_id"]
    anchor_pages = sorted(int(page) for page in anchor_group.get("pages", []) if isinstance(page, int))

    used_pages: set[int] = set()
    group_page_remap: dict[str, dict[int, int]] = {}
    group_anchor_page_map: dict[str, dict[int, int]] = {}
    ordered_groups = sorted(
        groups,
        key=lambda payload: 0 if payload.get("group_id") == anchor_group_id else 1,
    )
    ordered_group_ids = [payload["group_id"] for payload in ordered_groups]
    for payload in ordered_groups:
        group_id = payload["group_id"]
        order_index = ordered_group_ids.index(group_id)
        source_pages = [int(page) for page in payload.get("pages", []) if isinstance(page, int)]
        remap: dict[int, int] = {}
        for page in source_pages:
            virtual_page = page
            if virtual_page in used_pages:
                virtual_page = (order_index + 1) * 10000 + page
            while virtual_page in used_pages:
                virtual_page += 1
            remap[page] = virtual_page
            used_pages.add(virtual_page)
        group_page_remap[group_id] = remap
        if group_id == anchor_group_id:
            group_anchor_page_map[group_id] = {page: page for page in source_pages}
        else:
            group_anchor_page_map[group_id] = build_page_linear_remap(source_pages, anchor_pages)

    pages = sorted(used_pages)
    page_entries: dict[int, dict] = {}
    page_group_members: dict[str, list[str]] = {}
    person_id_map: dict[tuple[str, str], str] = {}
    for payload in groups:
        group_id = payload["group_id"]
        for person in payload.get("persons", []):
            source_person_id = str(person.get("id"))
            person_id_map[(group_id, source_person_id)] = merge_workspace_person_id(group_id, source_person_id)

    bridge_edges = []
    internal_edges = []
    merged_persons = []
    for payload in groups:
        group_id = payload["group_id"]
        page_remap = group_page_remap[group_id]
        anchor_map = group_anchor_page_map[group_id]
        for page_entry in payload.get("pages_data", []):
            original_page = page_entry.get("page")
            if not isinstance(original_page, int):
                continue
            virtual_page = page_remap.get(original_page)
            if not isinstance(virtual_page, int):
                continue
            page_group_members[str(virtual_page)] = [group_id]
            page_entries[virtual_page] = {
                **page_entry,
                "page": virtual_page,
                "source_page": original_page,
                "source_group_id": group_id,
                "anchor_page": anchor_map.get(original_page, original_page),
                "page_display_label": f"第{anchor_map.get(original_page, original_page)}页",
            }
        page_remap_for_group = group_page_remap[group_id]
        merged_persons.extend(
            [
                remap_person_pages(
                    person,
                    page_remap,
                    group_id,
                    merged_person_id=person_id_map[(group_id, str(person.get("id")))],
                    source_person_id=str(person.get("id")),
                )
                for person in payload.get("persons", [])
            ]
        )
        for edge in payload.get("edges", []):
            from_raw = str(edge.get("from_person_id") or "")
            to_raw = str(edge.get("to_person_id") or "")
            from_id = person_id_map.get((group_id, from_raw))
            to_id = person_id_map.get((group_id, to_raw))
            if not from_id or not to_id:
                continue
            internal_edges.append(
                remap_edge_pages_and_ids(
                    edge,
                    page_remap_for_group,
                    from_person_id=from_id,
                    to_person_id=to_id,
                )
            )

    for index in range(len(source_group_ids) - 1):
        left_group_id = source_group_ids[index]
        right_group_id = source_group_ids[index + 1]
        bridge_page_remap = {
            **group_page_remap.get(left_group_id, {}),
            **group_page_remap.get(right_group_id, {}),
        }
        db_bridge_edges = load_bridge_edges_from_sqlite(left_group_id, right_group_id)
        if db_bridge_edges:
            candidate_edges = db_bridge_edges
        else:
            candidate_edges = ensure_bridge_payload(left_group_id, right_group_id).get("edges", [])
        for edge in candidate_edges:
            from_raw = str(edge.get("from_person_id") or "")
            to_raw = str(edge.get("to_person_id") or "")
            from_group = str(edge.get("from_source_group_id") or "")
            to_group = str(edge.get("to_source_group_id") or "")
            from_id = None
            to_id = None
            if from_group:
                from_id = person_id_map.get((from_group, from_raw))
            if to_group:
                to_id = person_id_map.get((to_group, to_raw))
            if not from_id:
                from_id = person_id_map.get((left_group_id, from_raw)) or person_id_map.get((right_group_id, from_raw))
            if not to_id:
                to_id = person_id_map.get((left_group_id, to_raw)) or person_id_map.get((right_group_id, to_raw))
            if not from_id or not to_id:
                continue
            bridge_edges.append(
                remap_edge_pages_and_ids(
                    edge,
                    bridge_page_remap,
                    from_person_id=from_id,
                    to_person_id=to_id,
                )
            )

    merged = {
        "group_id": f"{MERGE_WORKSPACE_PREFIX}{'__'.join(source_group_ids)}",
        "workspace_type": "merge",
        "label": label_for_group_range(source_group_ids),
        "source_groups": source_group_ids,
        "anchor_group_id": anchor_group_id,
        "pages": pages,
        "persons": merged_persons,
        "edges": internal_edges + bridge_edges,
        "pages_data": [page_entries.get(page, {"page": page, "image": "", "source_group_id": anchor_group_id, "source_page": page, "anchor_page": page, "page_display_label": f"第{page}页"}) for page in pages],
        "page_group_members": page_group_members,
    }
    merged["generations"] = sorted({int(person.get("generation", 0)) for person in merged["persons"] if int(person.get("generation", 0) or 0) > 0})
    return merged


def payload_for_group(group_param: str | None) -> dict:
    merge_source_group_ids = parse_merge_workspace_id(group_param)
    if merge_source_group_ids:
        return build_merge_workspace_payload(merge_source_group_ids)
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
    return payload


def group_json_path(group_id: str) -> Path:
    return workspace_group_json_path(group_id)


def load_group_payload(group_id: str) -> dict:
    return json.loads(group_json_path(group_id).read_text(encoding="utf-8"))


def save_group_payload(group_id: str, payload: dict) -> Path:
    path = group_json_path(group_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_group_payload_from_db(group_id: str) -> dict:
    json_payload = load_group_payload(group_id)
    json_people = {str(person.get("id")): person for person in json_payload.get("persons", [])}
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
            SELECT id, source_person_id, name, generation, root_order, primary_page_no, primary_page_image_path,
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
            SELECT pp.source_person_id AS parent_source_person_id,
                   cp.source_person_id AS child_source_person_id,
                   r.relation_type, r.birth_order_under_parent,
                   r.confidence, r.page_sources_json, r.notes_json, r.is_verified, r.verified_at, r.remark
            FROM relationships AS r
            JOIN persons AS pp
              ON pp.id = r.parent_person_id
            JOIN persons AS cp
              ON cp.id = r.child_person_id
            WHERE r.scope = 'group_internal' AND r.scope_ref = ?
            ORDER BY pp.source_person_id, r.birth_order_under_parent, cp.source_person_id
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
        source_person_id = str(row["source_person_id"])
        json_person = json_people.get(source_person_id, {})
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        poly = json.loads(row["poly_json"]) if row["poly_json"] else None
        text_refs = json_person.get("text_refs")
        text_ref = json_person.get("text_ref")
        if not text_refs and row["primary_page_no"] and bbox:
            text_ref = {
                "page": row["primary_page_no"],
                "index": source_person_id,
                "text": row["name"],
                "box": bbox,
                "poly": poly,
            }
            text_refs = [text_ref]
        persons.append(
            {
                **json_person,
                "id": source_person_id,
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
                "from_person_id": row["parent_source_person_id"],
                "to_person_id": row["child_source_person_id"],
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


def find_person_payload(group_id: str, source_person_id: str) -> tuple[dict, dict, dict]:
    payload = load_group_payload(group_id)
    person = next((item for item in payload.get("persons", []) if str(item.get("id")) == str(source_person_id)), None)
    if not person:
        raise KeyError(f"Person {source_person_id} not found in {group_id}")
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
              p.source_person_id,
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

    payload, person, pages_by_no = find_person_payload(row["group_id"], row["source_person_id"])
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
            "source_person_id": row["source_person_id"],
            "group_id": row["group_id"],
            "name": row["name"] or person.get("name"),
            "canonical_name": row["canonical_name"],
            "generation": row["generation"] or person.get("generation"),
            "root_order": row["root_order"] or person.get("root_order"),
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
        row = conn.execute(
            "SELECT id, group_id, source_person_id FROM persons WHERE id = ?",
            (person_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": f"未找到人物 {person_id}"}

    notes: list[str] = []
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT notes_json FROM persons WHERE id = ?",
            (person_id,),
        ).fetchone()
        if existing and existing["notes_json"]:
            try:
                notes = [str(item) for item in json.loads(existing["notes_json"] or "[]")]
            except json.JSONDecodeError:
                notes = []
        if "人工更正姓名" not in notes:
            notes.append("人工更正姓名")
        conn.execute(
            """
            UPDATE persons
            SET name = ?, canonical_name = ?, notes_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (cleaned_name, cleaned_name, json.dumps(notes, ensure_ascii=False), person_id),
        )
        conn.commit()
    finally:
        conn.close()
    detail = build_person_detail_payload(row["id"])
    return {"ok": True, "mode": "db_direct", "detail": detail}


def crop_person_glyph(person_id: str) -> dict:
    detail = build_person_detail_payload(person_id)
    if not detail.get("ok"):
        return detail
    person = detail["person"]
    glyph_image_path = person.get("glyph_image")
    if glyph_image_path:
        local_glyph_path = resolve_repo_asset_path(str(glyph_image_path))
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

    image_path = resolve_repo_asset_path(str(page_image_path))
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
        group_jsons = [
            path
            for group_dir in iter_group_dirs("gen_*")
            for path in [group_dir / "group_template.json"]
            if path.name == "group_template.json" and group_within_complete_tree(path)
        ]
        bridge_jsons = [
            path
            for path in sorted(BRIDGE_DIR.glob("*.json"))
            if bridge_within_complete_tree(path)
        ]
        db_path = sync_workspace_to_sqlite(
            db_path=SQLITE_DB_PATH,
            group_jsons=group_jsons,
            bridge_jsons=bridge_jsons,
            reset=True,
        )
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
        completion_rows = conn.execute(
            """
            SELECT group_id, missing_parent_count
            FROM v_group_completion
            """
        ).fetchall()
        range_missing_parent_count = 0
        for row in completion_rows:
            group_id = row[0]
            _, end_generation = parse_group_range(group_id)
            if end_generation is None:
                continue
            if end_generation <= COMPLETE_TREE_MAX_GENERATION:
                range_missing_parent_count += int(row[1] or 0)
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


def query_full_tree_payload(max_generation: int = COMPLETE_TREE_MAX_GENERATION) -> dict:
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
                "glyph_image": (
                    f"/{str(row['glyph_asset_path']).lstrip('/')}"
                    if row["glyph_asset_path"]
                    else ""
                ),
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


def bio_project_meta_list() -> list[dict]:
    rows = []
    for project_id, project_dir in sorted(BIO_PROJECT_DIRS.items()):
        if not bio_project_accessible(project_dir):
            continue
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


def current_bio_person_catalog(max_generation: int = COMPLETE_TREE_MAX_GENERATION) -> list[dict]:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              p.id,
              p.name,
              p.generation,
              p.group_id,
              p.primary_page_no,
              COALESCE(
                json_group_array(DISTINCT parent.name)
                  FILTER (WHERE parent.name IS NOT NULL),
                '[]'
              ) AS parent_names_json
            FROM persons AS p
            LEFT JOIN relationships AS r
              ON r.child_person_id = p.id
            LEFT JOIN persons AS parent
              ON parent.id = r.parent_person_id
            WHERE p.generation BETWEEN 1 AND ?
            GROUP BY p.id
            ORDER BY p.generation, p.primary_page_no, p.id
            """,
            (max_generation,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "person_id": row["id"],
            "name": row["name"],
            "generation": row["generation"],
            "group_id": row["group_id"],
            "primary_page_no": row["primary_page_no"],
            "parent_names": json.loads(row["parent_names_json"] or "[]"),
        }
        for row in rows
    ]


def refresh_bio_bundle_person_names(bundle: dict, catalog: list[dict]) -> dict:
    person_by_id = {item["person_id"]: item for item in catalog}
    bundle["person_catalog"] = catalog
    for page in bundle.get("pages", []):
        for match in page.get("matches", []):
            recommended_id = match.get("recommended_person_id")
            recommended = person_by_id.get(recommended_id)
            if recommended:
                match["recommended_person_name"] = recommended["name"]
            refreshed_candidates = []
            for candidate in match.get("candidates", []):
                person = person_by_id.get(candidate.get("person_id"))
                refreshed_candidates.append({**candidate, **person} if person else candidate)
            match["candidates"] = refreshed_candidates
    return bundle


def current_bio_linked_person_ids() -> list[str]:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT person_id
            FROM person_biographies
            WHERE match_status = 'reviewed_manual'
            ORDER BY person_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def bio_bundle_for_client(project_id: str) -> dict:
    project_dir = resolve_bio_project_dir(project_id)
    if not bio_project_accessible(project_dir):
        raise PermissionError(f"Biography project is not accessible: {project_dir}")
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
    bundle["generation_range"] = [1, COMPLETE_TREE_MAX_GENERATION]
    refresh_bio_bundle_person_names(bundle, current_bio_person_catalog(COMPLETE_TREE_MAX_GENERATION))
    bundle["linked_person_ids"] = current_bio_linked_person_ids()
    return bundle


class ReviewHandler(SimpleHTTPRequestHandler):
    @staticmethod
    def resolve_bio_ui_dir() -> Path:
        if BIO_REVIEW_UI_DIR.exists():
            return BIO_REVIEW_UI_DIR
        default_project_dir = resolve_bio_project_dir(None)
        return default_project_dir / "review"

    def address_string(self) -> str:
        return self.client_address[0]

    def end_headers(self) -> None:
        parsed_path = urlparse(self.path).path
        if parsed_path == "/review" or parsed_path.startswith("/review/"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        path = urlparse(path).path
        if path in {"/review", "/review/"}:
            return str((self.resolve_bio_ui_dir() / "index.html").resolve())
        if path.startswith("/review/"):
            relative = path[len("/review/") :]
            return str((self.resolve_bio_ui_dir() / relative).resolve())
        for project_id, project_dir in BIO_PROJECT_DIRS.items():
            prefix = f"/{project_id}/"
            if path.startswith(prefix):
                relative = path[len(prefix) :]
                return str((project_dir / relative).resolve())
        if path in {"/", "/editor", "/editor/"}:
            return str((GEN_EDITOR_UI_DIR / "index.html").resolve())
        if path.startswith("/editor/"):
            relative = path[len("/editor/") :]
            return str((GEN_EDITOR_UI_DIR / relative).resolve())
        if path.startswith("/gen_093_097/editor/"):
            relative = path[len("/gen_093_097/editor/") :]
            return str((GEN_EDITOR_UI_DIR / relative).resolve())
        return str(resolve_repo_asset_path(path).resolve())

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
                if not bio_project_accessible(project_dir):
                    raise PermissionError(f"Biography project is not accessible: {project_dir}")
            except KeyError:
                body = json.dumps({"error": "unknown_project"}, ensure_ascii=False).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except PermissionError as exc:
                body = json.dumps({"error": "project_not_accessible", "detail": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            bundle = bio_bundle_for_client(str(project_id))
            state = build_bio_state_from_sqlite(bundle, project_id=str(project_id))
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
            max_generation_raw = query.get("max_generation", [str(COMPLETE_TREE_MAX_GENERATION)])[0]
            max_generation = int(max_generation_raw) if str(max_generation_raw).isdigit() else COMPLETE_TREE_MAX_GENERATION
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
            bundle = load_bio_json(bundle_path, {})
            normalized = normalize_bio_state(bundle, payload, project_dir)
            sync_bio_state_to_sqlite(bundle, normalized, project_dir)
            body = json.dumps({"ok": True, "mode": "db_only"}, ensure_ascii=False).encode("utf-8")
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
            virtual_to_source_page = {}
            for page_entry in data.get("pages_data", []):
                if not isinstance(page_entry, dict):
                    continue
                virtual_page = page_entry.get("page")
                source_page = page_entry.get("source_page", virtual_page)
                if isinstance(virtual_page, int) and isinstance(source_page, int):
                    virtual_to_source_page[virtual_page] = source_page

            person_source_lookup = {}
            group_people = {}
            for person in data.get("persons", []):
                if not isinstance(person, dict):
                    continue
                merged_person_id = str(person.get("id") or "")
                source_group_id = str(person.get("source_group_id") or "")
                source_person_id = str(person.get("source_person_id") or "")
                if not merged_person_id or not source_group_id:
                    continue
                if not source_person_id:
                    if "::" in merged_person_id:
                        source_person_id = merged_person_id.split("::", 1)[1]
                    else:
                        source_person_id = merged_person_id
                person_source_lookup[merged_person_id] = {
                    "source_group_id": source_group_id,
                    "source_person_id": source_person_id,
                }
                group_people.setdefault(source_group_id, set()).add(merged_person_id)

            def normalize_merge_edge(edge: dict) -> dict:
                copied = dict(edge)
                if isinstance(copied.get("page_sources"), list):
                    copied["page_sources"] = [
                        virtual_to_source_page.get(page, page) if isinstance(page, int) else page
                        for page in copied["page_sources"]
                    ]
                from_lookup = person_source_lookup.get(str(copied.get("from_person_id") or ""))
                to_lookup = person_source_lookup.get(str(copied.get("to_person_id") or ""))
                if from_lookup:
                    copied["from_person_id"] = from_lookup["source_person_id"]
                if to_lookup:
                    copied["to_person_id"] = to_lookup["source_person_id"]
                return copied

            bridge_write_stats = []
            for index in range(len(merge_source_group_ids) - 1):
                left_group_id = merge_source_group_ids[index]
                right_group_id = merge_source_group_ids[index + 1]
                left_ids = group_people.get(left_group_id, set())
                right_ids = group_people.get(right_group_id, set())
                bridge_edges = []
                for edge in data.get("edges", []):
                    from_id = edge.get("from_person_id")
                    to_id = edge.get("to_person_id")
                    if not (
                        (from_id in left_ids and to_id in right_ids)
                        or (from_id in right_ids and to_id in left_ids)
                    ):
                        continue
                    normalized = normalize_merge_edge(edge)
                    from_lookup = person_source_lookup.get(str(from_id))
                    to_lookup = person_source_lookup.get(str(to_id))
                    if not from_lookup or not to_lookup:
                        continue
                    normalized["from_source_group_id"] = from_lookup["source_group_id"]
                    normalized["to_source_group_id"] = to_lookup["source_group_id"]
                    bridge_edges.append(normalized)
                upserted = upsert_bridge_edges_to_sqlite(left_group_id, right_group_id, bridge_edges)
                bridge_write_stats.append(
                    {
                        "pair": f"{left_group_id}__{right_group_id}",
                        "scope_ref": bridge_scope_ref(left_group_id, right_group_id),
                        "edge_count": upserted,
                    }
                )
            mirror = current_sqlite_mirror_summary()
            body = json.dumps(
                {"ok": True, "mode": "db_direct", "bridge_updates": bridge_write_stats, "sqlite_mirror": mirror},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        sync_group_payload_to_sqlite(
            db_path=SQLITE_DB_PATH,
            payload=data,
            glyph_dir=GLYPH_ASSET_DIR,
        )
        bridge_updates = restore_related_bridges_to_sqlite(data.get("group_id"))
        body = json.dumps(
            {
                "ok": True,
                "mode": "db_direct",
                "group_id": data.get("group_id"),
                "db_path": str(SQLITE_DB_PATH),
                "bridge_updates": bridge_updates,
            },
            ensure_ascii=False,
        ).encode("utf-8")
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
        for path in iter_bio_project_dirs()
        if bio_project_accessible(path.resolve())
    }
    BIO_DEFAULT_PROJECT_ID = sorted(BIO_PROJECT_DIRS.keys())[0] if BIO_PROJECT_DIRS else None
    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"Serving review app at http://{args.host}:{args.port}")
    print(f"Using group data: {GROUP_JSON}")
    print(f"Serving editor UI from: {GEN_EDITOR_UI_DIR}")
    if BIO_DEFAULT_PROJECT_ID:
        print(f"Serving biography review at http://{args.host}:{args.port}/review/")
        print(f"Serving biography UI from: {BIO_REVIEW_UI_DIR}")
    try:
      server.serve_forever()
    except KeyboardInterrupt:
      pass
    finally:
      server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
