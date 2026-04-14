#!/usr/bin/env python3

from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "genealogy.sqlite"

VARIANT_CHAR_MAP = str.maketrans(
    {
        "简": "簡",
        "眛": "昧",
        "开": "開",
        "汉": "漢",
        "礼": "禮",
        "达": "達",
        "泾": "涇",
        "渊": "淵",
        "浅": "淺",
        "广": "廣",
        "寿": "壽",
        "宝": "寶",
    }
)


@dataclass
class PersonRow:
    person_id: str
    name: str
    generation: int
    group_id: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build person match candidates for biography title OCR results.")
    parser.add_argument("--project-json", type=Path, required=True, help="Path to biography project.json")
    parser.add_argument("--ocr-dir", type=Path, required=True, help="Directory with page_XXX.paddleocr.json files")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB, help="SQLite path")
    parser.add_argument("--generation-start", type=int, default=1)
    parser.add_argument("--generation-end", type=int, default=92)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    return parser


def normalize_name(text: str) -> str:
    return text.translate(VARIANT_CHAR_MAP).strip()


def looks_like_noise(text: str, score: float) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if score < 0.5:
        return True
    if re.search(r"[0-9A-Za-z]", cleaned):
        return True
    if len(cleaned) == 1:
        return True
    return False


def fetch_people(conn: sqlite3.Connection, start: int, end: int) -> list[PersonRow]:
    rows = conn.execute(
        """
        select id, name, generation, group_id
        from persons
        where generation between ? and ?
        order by generation, id
        """,
        (start, end),
    ).fetchall()
    return [PersonRow(*row) for row in rows]


def person_dict(person: PersonRow) -> dict:
    return {
        "person_id": person.person_id,
        "name": person.name,
        "generation": person.generation,
        "group_id": person.group_id,
    }


def build_candidates(title: str, people: list[PersonRow], by_name: dict[str, list[PersonRow]], by_normalized: dict[str, list[PersonRow]]) -> tuple[str, list[dict], str | None]:
    exact_rows = by_name.get(title, [])
    if len(exact_rows) == 1:
        return "exact_unique", [person_dict(exact_rows[0])], exact_rows[0].person_id
    if len(exact_rows) > 1:
        return "exact_multiple", [person_dict(row) for row in exact_rows], None

    normalized = normalize_name(title)
    if normalized != title:
        norm_rows = by_name.get(normalized, [])
        if len(norm_rows) == 1:
            return "normalized_unique", [person_dict(norm_rows[0])], norm_rows[0].person_id
        if len(norm_rows) > 1:
            return "normalized_multiple", [person_dict(row) for row in norm_rows], None

    norm_bucket = by_normalized.get(normalized, [])
    if len(norm_bucket) == 1:
        return "normalized_bucket_unique", [person_dict(norm_bucket[0])], norm_bucket[0].person_id
    if len(norm_bucket) > 1:
        return "normalized_bucket_multiple", [person_dict(row) for row in norm_bucket], None

    name_choices = [person.name for person in people]
    fuzzy_names = difflib.get_close_matches(normalized, name_choices, n=5, cutoff=0.3)
    fuzzy_rows: list[dict] = []
    seen = set()
    for candidate_name in fuzzy_names:
        for row in by_name.get(candidate_name, []):
            if row.person_id in seen:
                continue
            fuzzy_rows.append(person_dict(row))
            seen.add(row.person_id)
    return "fuzzy", fuzzy_rows, None


def build_markdown(project_label: str, pages: list[dict], stats: dict) -> str:
    lines = [
        f"# {project_label} Step 2 匹配清单",
        "",
        "## 统计",
        "",
        f"- 标题候选总数：`{stats['title_count']}`",
        f"- 可直接自动挂接：`{stats['auto_match_count']}`",
        f"- 需人工复核：`{stats['manual_review_count']}`",
        f"- 疑似噪音：`{stats['noise_count']}`",
        "",
        "## 页面明细",
        "",
    ]
    for page in pages:
        lines.extend([f"### 第{page['page']}页", ""])
        for item in page["matches"]:
            title = item["ocr_title"]
            score = item["ocr_score"]
            status = item["match_status"]
            recommended = item.get("recommended_person_id") or "待定"
            candidates = item.get("candidates", [])
            candidate_text = "；".join(
                f"{row['name']}({row['person_id']}, {row['generation']}世)"
                for row in candidates[:5]
            ) or "无"
            lines.append(f"- `{title}` | score=`{score:.4f}` | status=`{status}` | 推荐=`{recommended}` | 候选：{candidate_text}")
        if not page["matches"]:
            lines.append("- 本页无标题候选")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    conn = sqlite3.connect(str(args.db_path.resolve()))
    people = fetch_people(conn, args.generation_start, args.generation_end)
    by_name: dict[str, list[PersonRow]] = {}
    by_normalized: dict[str, list[PersonRow]] = {}
    for person in people:
        by_name.setdefault(person.name, []).append(person)
        by_normalized.setdefault(normalize_name(person.name), []).append(person)

    project = json.loads(args.project_json.resolve().read_text(encoding="utf-8"))
    pages_payload = []
    title_count = 0
    auto_match_count = 0
    manual_review_count = 0
    noise_count = 0

    for page_entry in project.get("pages_data", []):
        page_no = int(page_entry["page"])
        ocr_path = args.ocr_dir.resolve() / f"page_{page_no:03d}.paddleocr.json"
        if not ocr_path.exists():
            continue
        ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
        matches = []
        for item in ocr_data.get("title_candidates", []):
            title = item["text"].strip()
            score = float(item["score"])
            title_count += 1
            if looks_like_noise(title, score):
                matches.append(
                    {
                        "ocr_index": item.get("index"),
                        "ocr_title": title,
                        "ocr_score": score,
                        "match_status": "noise",
                        "recommended_person_id": None,
                        "candidates": [],
                    }
                )
                noise_count += 1
                continue

            match_status, candidates, recommended = build_candidates(title, people, by_name, by_normalized)
            if recommended:
                auto_match_count += 1
            else:
                manual_review_count += 1
            matches.append(
                {
                    "ocr_index": item.get("index"),
                    "ocr_title": title,
                    "ocr_score": score,
                    "match_status": match_status,
                    "recommended_person_id": recommended,
                    "candidates": candidates,
                }
            )
        pages_payload.append({"page": page_no, "matches": matches})

    payload = {
        "project_id": project.get("project_id"),
        "label": project.get("label"),
        "generation_range": [args.generation_start, args.generation_end],
        "person_catalog": [
            person_dict(person)
            for person in people
        ],
        "stats": {
            "title_count": title_count,
            "auto_match_count": auto_match_count,
            "manual_review_count": manual_review_count,
            "noise_count": noise_count,
        },
        "pages": pages_payload,
    }

    args.out_json.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.resolve().write_text(
        build_markdown(project.get("label", "人物小传"), pages_payload, payload["stats"]) + "\n",
        encoding="utf-8",
    )
    print(args.out_json.resolve())
    print(args.out_md.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
