#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2  # type: ignore

from import_genealogy_to_sqlite import DEFAULT_DB_PATH


ROOT = Path(__file__).resolve().parents[1]
SQLITE_DB_PATH = DEFAULT_DB_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local review server for biography project.")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8876)
    return parser


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_page_state(page_state: dict) -> dict:
    page_state.setdefault("deleted_ocr_indexes", [])
    page_state.setdefault("title_assignments", {})
    page_state.setdefault("manual_matches", [])
    page_state.setdefault("biographies", [])
    return page_state


def crop_block_image(
    project_dir: Path,
    page: dict,
    item: dict,
    bio_index: int,
    block_index: int,
    source_page_no: int | None = None,
) -> str | None:
    image_path = project_dir / page["raw_image"]
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    x1, y1, x2, y2 = item["box"]
    x1 = max(0, int(round(x1)))
    y1 = max(0, int(round(y1)))
    x2 = min(image.shape[1], int(round(x2)))
    y2 = min(image.shape[0], int(round(y2)))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image[y1:y2, x1:x2]
    crop_page_no = int(source_page_no or page["page"])
    crop_dir = project_dir / "review" / "crops" / f"page_{crop_page_no:03d}"
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_path = crop_dir / f"bio_{bio_index:03d}_block_{block_index:03d}_idx_{item['index']:03d}.png"
    cv2.imwrite(str(crop_path), crop)
    return str(crop_path.relative_to(project_dir))


def parse_block_key(raw_key: str) -> tuple[int, int] | None:
    try:
        page_no_str, index_str = str(raw_key).split(":", 1)
        return int(page_no_str), int(index_str)
    except (TypeError, ValueError):
        return None


def normalize_state(bundle: dict, state: dict, project_dir: Path) -> dict:
    page_map = {str(page["page"]): page for page in bundle.get("pages", [])}
    person_catalog = {item["person_id"]: item for item in bundle.get("person_catalog", [])}
    state.setdefault("project_id", bundle.get("project_id"))
    state.setdefault("pages", {})

    ocr_cache: dict[str, dict[int, dict]] = {}
    for page_key, page in page_map.items():
        ocr_data = load_json(project_dir / page["ocr_json"], {})
        ocr_cache[page_key] = {int(item["index"]): item for item in ocr_data.get("ordered_items", [])}

    for page_key, page in page_map.items():
        page_state = ensure_page_state(state["pages"].setdefault(page_key, {}))
        deleted = {int(idx) for idx in page_state.get("deleted_ocr_indexes", [])}

        normalized_biographies = []
        for bio_index, biography in enumerate(page_state.get("biographies", [])):
            raw_block_keys = biography.get("selected_block_keys") or []
            selected_blocks: list[tuple[int, int]] = []
            seen_blocks: set[tuple[int, int]] = set()

            for raw_key in raw_block_keys:
                parsed = parse_block_key(raw_key)
                if not parsed:
                    continue
                source_page_no, ocr_index = parsed
                source_page_state = ensure_page_state(state["pages"].setdefault(str(source_page_no), {}))
                source_deleted = {int(idx) for idx in source_page_state.get("deleted_ocr_indexes", [])}
                if source_page_no == int(page_key) and ocr_index in deleted:
                    continue
                if ocr_index in source_deleted:
                    continue
                source_item_map = ocr_cache.get(str(source_page_no), {})
                if ocr_index not in source_item_map:
                    continue
                block_ref = (source_page_no, ocr_index)
                if block_ref in seen_blocks:
                    continue
                seen_blocks.add(block_ref)
                selected_blocks.append(block_ref)

            if not selected_blocks:
                fallback_indexes = biography.get("selected_ocr_indexes", []) or []
                normalized_indexes = []
                for raw_idx in fallback_indexes:
                    try:
                        ocr_index = int(raw_idx)
                    except (TypeError, ValueError):
                        continue
                    if ocr_index in deleted or ocr_index not in ocr_cache.get(page_key, {}):
                        continue
                    normalized_indexes.append(ocr_index)
                for ocr_index in sorted(dict.fromkeys(normalized_indexes)):
                    block_ref = (int(page_key), ocr_index)
                    if block_ref in seen_blocks:
                        continue
                    seen_blocks.add(block_ref)
                    selected_blocks.append(block_ref)

            source_blocks = []
            joined_text_parts = []
            selected_indexes = []
            source_pages = []
            for block_index, (source_page_no, ocr_index) in enumerate(selected_blocks):
                source_page = page_map.get(str(source_page_no))
                source_item = ocr_cache.get(str(source_page_no), {}).get(ocr_index)
                if not source_page or not source_item:
                    continue
                crop_image = crop_block_image(
                    project_dir,
                    source_page,
                    source_item,
                    bio_index,
                    block_index,
                    source_page_no=source_page_no,
                )
                source_blocks.append(
                    {
                        "page_no": source_page_no,
                        "ocr_index": ocr_index,
                        "text": source_item["text"],
                        "box": source_item["box"],
                        "crop_image": crop_image,
                    }
                )
                joined_text_parts.append(source_item["text"])
                if source_page_no == int(page_key):
                    selected_indexes.append(ocr_index)
                if source_page_no not in source_pages:
                    source_pages.append(source_page_no)

            linear_text = (biography.get("linear_text") or "").strip() or "".join(joined_text_parts)
            person_id = biography.get("person_id")
            normalized_biographies.append(
                {
                    "person_id": person_id,
                    "person_name": person_catalog.get(person_id, {}).get("name"),
                    "selected_ocr_indexes": selected_indexes,
                    "selected_block_keys": [f"{source_page_no}:{ocr_index}" for source_page_no, ocr_index in selected_blocks],
                    "source_pages": source_pages or [int(page_key)],
                    "source_blocks": source_blocks,
                    "ocr_texts": [item["text"] for item in source_blocks],
                    "linear_text": linear_text,
                    "baihua_text": biography.get("baihua_text") or "",
                }
            )
        page_state["biographies"] = normalized_biographies
    return state


def sync_state_to_sqlite(bundle: dict, state: dict, project_dir: Path) -> None:
    project_id = bundle.get("project_id")
    page_bundle_map = {str(page["page"]): page for page in bundle.get("pages", [])}
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    try:
        for page_key, page in page_bundle_map.items():
            page_no = int(page["page"])
            page_state = ensure_page_state(state["pages"].get(page_key, {}))
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
                    page_no,
                    str((project_dir / page["raw_image"]).resolve()),
                    None,
                    str((project_dir / page["ocr_json"]).resolve()) if page.get("ocr_json") else None,
                    "reviewed" if page_state.get("biographies") else page.get("review_status") or "draft",
                    json.dumps([], ensure_ascii=False),
                ),
            )

        conn.execute(
            """
            DELETE FROM person_biographies
            WHERE project_id = ? AND match_status = 'reviewed_manual'
            """,
            (project_id,),
        )

        for page_key, page_state in state.get("pages", {}).items():
            page = page_bundle_map.get(str(page_key))
            if not page:
                continue
            page_no = int(page_key)
            source_image_path = str((project_dir / page["raw_image"]).resolve())
            for biography in page_state.get("biographies", []):
                person_id = biography.get("person_id")
                if not person_id:
                    continue
                source_blocks = biography.get("source_blocks") or []
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
                      source_columns_json = excluded.source_columns_json,
                      source_text_raw = excluded.source_text_raw,
                      source_text_linear = excluded.source_text_linear,
                      source_text_punctuated = excluded.source_text_punctuated,
                      source_text_baihua = excluded.source_text_baihua,
                      source_text_translation_notes = excluded.source_text_translation_notes,
                      match_status = excluded.match_status,
                      match_confidence = excluded.match_confidence,
                      notes_json = excluded.notes_json,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        person_id,
                        project_id,
                        page_no,
                        source_image_path,
                        biography.get("person_name") or biography.get("person_id"),
                        json.dumps(source_blocks, ensure_ascii=False),
                        json.dumps(biography.get("ocr_texts") or [], ensure_ascii=False),
                        biography.get("linear_text") or "",
                        biography.get("linear_text") or "",
                        biography.get("baihua_text") or "",
                        None,
                        "reviewed_manual",
                        1.0,
                        json.dumps(
                            {
                                "selected_ocr_indexes": biography.get("selected_ocr_indexes") or [],
                                "selected_block_keys": biography.get("selected_block_keys") or [],
                                "source_pages": biography.get("source_pages") or [page_no],
                                "crop_images": [item.get("crop_image") for item in source_blocks],
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def build_initial_state(bundle: dict) -> dict:
    pages = {}
    for page in bundle.get("pages", []):
        title_assignments = {}
        for item in page.get("matches", []):
            key = str(item.get("ocr_index"))
            title_assignments[key] = {
                "ocr_title": item.get("ocr_title"),
                "selected_person_id": item.get("recommended_person_id"),
                "match_status": item.get("match_status"),
            }
        pages[str(page["page"])] = {
            "deleted_ocr_indexes": [],
            "title_assignments": title_assignments,
            "manual_matches": [],
            "biographies": [],
        }
    return {
        "project_id": bundle.get("project_id"),
        "pages": pages,
    }


class BiographyReviewHandler(SimpleHTTPRequestHandler):
    root_dir: Path
    ui_dir: Path
    default_project_id: str
    project_dirs: dict[str, Path]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.root_dir), **kwargs)

    # Avoid reverse DNS lookup for LAN clients. BaseHTTPRequestHandler may block
    # on hostname resolution for non-loopback addresses, which makes requests
    # appear to hang even though the TCP connection is established.
    def address_string(self) -> str:
        return self.client_address[0]

    @classmethod
    def resolve_project_dir(cls, project_id: str | None) -> Path:
        effective_project_id = project_id or cls.default_project_id
        project_dir = cls.project_dirs.get(effective_project_id)
        if project_dir is None:
            raise KeyError(f"Unknown biography project: {effective_project_id}")
        return project_dir

    @classmethod
    def ensure_state(cls, project_id: str | None = None) -> Path:
        project_dir = cls.resolve_project_dir(project_id)
        review_dir = project_dir / "review"
        bundle_path = review_dir / "review_data.json"
        state_path = review_dir / "review_state.json"
        bundle = load_json(bundle_path, {})
        if not state_path.exists():
            state_path.write_text(
                json.dumps(build_initial_state(bundle), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return state_path

    @classmethod
    def project_meta_list(cls) -> list[dict]:
        rows = []
        for project_id, project_dir in sorted(cls.project_dirs.items()):
            project = load_json(project_dir / "project.json", {})
            rows.append(
                {
                    "project_id": project_id,
                    "label": project.get("label") or project_id,
                    "page_range": project.get("page_range") or [],
                    "source_pdf": Path(project.get("source_pdf") or "").name or None,
                }
            )
        return rows

    @classmethod
    def bundle_for_client(cls, project_id: str) -> dict:
        project_dir = cls.resolve_project_dir(project_id)
        bundle_path = project_dir / "review" / "review_data.json"
        bundle = load_json(bundle_path, {})
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

    def translate_path(self, path: str) -> str:
        parsed_path = urlparse(path).path
        if parsed_path in {"/review", "/review/"}:
            return str(self.ui_dir / "index.html")
        if parsed_path.startswith("/review/"):
            relative = parsed_path[len("/review/") :]
            return str(self.ui_dir / relative)
        return super().translate_path(path)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/review":
            self.send_response(301)
            self.send_header("Location", "/review/")
            self.end_headers()
            return
        if parsed.path == "/api/review-data":
            query = parse_qs(parsed.query)
            project_id = query.get("project_id", [self.default_project_id])[0]
            try:
                project_dir = self.resolve_project_dir(project_id)
            except KeyError:
                self._send_json({"error": "unknown_project"}, status=404)
                return
            state_path = self.ensure_state(project_id)
            bundle = self.bundle_for_client(project_id)
            state = load_json(state_path, {})
            self._send_json(
                {
                    "bundle": bundle,
                    "state": state,
                    "projects": self.project_meta_list(),
                    "selected_project_id": project_id,
                    "project_dir": str(project_dir),
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/save-state":
            self._send_json({"error": "not_found"}, status=404)
            return
        query = parse_qs(parsed.query)
        project_id = query.get("project_id", [None])[0]
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        effective_project_id = project_id or payload.get("project_id") or self.default_project_id
        try:
            project_dir = self.resolve_project_dir(effective_project_id)
        except KeyError:
            self._send_json({"error": "unknown_project"}, status=404)
            return
        bundle_path = project_dir / "review" / "review_data.json"
        state_path = self.ensure_state(effective_project_id)
        bundle = load_json(bundle_path, {})
        normalized = normalize_state(bundle, payload, project_dir)
        state_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sync_state_to_sqlite(bundle, normalized, project_dir)
        self._send_json({"ok": True})


def main() -> int:
    args = build_parser().parse_args()
    if args.project_dir:
        project_dirs = {args.project_dir.resolve().name: args.project_dir.resolve()}
    else:
        project_dirs = {
            path.name: path.resolve()
            for path in sorted(ROOT.glob("bio_*"))
            if (path / "project.json").exists() and (path / "review" / "review_data.json").exists()
        }
    if not project_dirs:
        raise SystemExit("No biography projects with review_data.json found.")
    default_project_id = sorted(project_dirs.keys())[0]
    BiographyReviewHandler.root_dir = ROOT
    BiographyReviewHandler.ui_dir = ROOT / default_project_id / "review"
    BiographyReviewHandler.default_project_id = default_project_id
    BiographyReviewHandler.project_dirs = project_dirs
    for project_id in project_dirs:
        BiographyReviewHandler.ensure_state(project_id)
    server = ThreadingHTTPServer((args.host, args.port), BiographyReviewHandler)
    print(f"Serving biography review at http://{args.host}:{args.port}/review/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
