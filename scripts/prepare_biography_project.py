#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "genealogy.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a page-by-page biography extraction project from a PDF.")
    parser.add_argument("--project-id", required=True, help="Project directory name, for example bio_001_092_qianbian")
    parser.add_argument("--label", required=True, help="Human-readable project label")
    parser.add_argument("--pdf", type=Path, required=True, help="Source PDF path")
    parser.add_argument("--start-page", type=int, required=True, help="Start page number in the PDF")
    parser.add_argument("--end-page", type=int, required=True, help="End page number in the PDF")
    parser.add_argument(
        "--expected-generations",
        default="",
        help="Expected generation range, for example 1-92. Stored as metadata only.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help="SQLite path used only to record the current person count in project metadata.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Ghostscript render DPI for JPG export.",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Skip PDF->JPG rendering and only build project files.",
    )
    return parser


def parse_generation_range(raw: str) -> list[int]:
    if not raw:
        return []
    if "-" not in raw:
        return [int(raw)]
    start, end = raw.split("-", 1)
    return [int(start), int(end)]


def fetch_person_count(db_path: Path, generation_range: list[int]) -> int | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        if len(generation_range) == 2:
            row = conn.execute(
                "SELECT COUNT(*) FROM persons WHERE generation BETWEEN ? AND ?",
                (generation_range[0], generation_range[1]),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM persons").fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def render_pages(pdf_path: Path, image_dir: Path, start_page: int, end_page: int, dpi: int) -> None:
    image_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = image_dir / "_render_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gs",
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-sDEVICE=jpeg",
        f"-r{dpi}",
        "-dJPEGQ=95",
        f"-dFirstPage={start_page}",
        f"-dLastPage={end_page}",
        f"-sOutputFile={tmp_dir / 'page_%03d.jpg'}",
        str(pdf_path),
    ]
    subprocess.run(cmd, check=True)
    for offset, page in enumerate(range(start_page, end_page + 1), start=1):
        source = tmp_dir / f"page_{offset:03d}.jpg"
        target = image_dir / f"page_{page:03d}.jpg"
        if not source.exists():
            raise FileNotFoundError(f"Missing rendered JPG: {source}")
        source.replace(target)
    shutil.rmtree(tmp_dir)


def build_project_payload(
    project_id: str,
    label: str,
    pdf_path: Path,
    image_dir: Path,
    start_page: int,
    end_page: int,
    generation_range: list[int],
    matched_person_count: int | None,
) -> dict:
    pages = list(range(start_page, end_page + 1))
    return {
        "project_id": project_id,
        "label": label,
        "source_pdf": str(pdf_path),
        "page_range": [start_page, end_page],
        "expected_generations": generation_range,
        "matched_person_count_hint": matched_person_count,
        "reading_order": {
            "columns": "top_to_bottom",
            "blocks": "right_to_left",
            "notes": [
                "页顶每一栏先识别人物标题。",
                "每个标题下方多列正文按从右到左拼接。",
                "列内文字按从上到下读取。",
            ],
        },
        "steps": [
            "step_1_page_level_ocr",
            "step_2_manual_person_matching",
            "step_3_linearize_punctuate_baihua_and_import",
        ],
        "pages": pages,
        "pages_data": [
            {
                "page": page,
                "image": str(image_dir / f"page_{page:03d}.jpg"),
                "ocr_items": [],
                "title_candidates": [],
                "biographies": [],
                "manual_notes": [],
                "review_status": "draft",
            }
            for page in pages
        ],
    }


def build_workflow_md(project_id: str, label: str, start_page: int, end_page: int, generation_range: list[int]) -> str:
    generation_text = (
        f"`{generation_range[0]}-{generation_range[1]}世`" if len(generation_range) == 2 else "`待补充`"
    )
    return "\n".join(
        [
            "# 人物小传工作流",
            "",
            "## 范围",
            "",
            f"- 项目编号：`{project_id}`",
            f"- 项目名称：`{label}`",
            f"- PDF 页码：`{start_page}-{end_page}`",
            f"- 目标世代：{generation_text}",
            "- 阅读顺序：`列内上到下，列间右到左`",
            "",
            "## 三步流程",
            "",
            "1. 逐页 OCR",
            "2. 人工核对标题人物，并关联到 SQLite `persons`",
            "3. 把竖排原文整理成横排断句文本，并补白话文，再写回数据库",
            "",
            "## 页内结构规则",
            "",
            "- 每页顶部若干大字栏为人物标题。",
            "- 每个标题下方对应若干竖列正文。",
            "- 正文不跨人物拼接；必须先定标题边界，再拼正文列。",
            "- OCR 阶段允许保留错字和缺字，但要保留列顺序与原始列文本。",
            "",
            "## 当前数据原则",
            "",
            "- `project.json` 保存逐页底稿。",
            "- 每页先只做识别，不急着断句。",
            "- 与既有人物库的关联在人工校对阶段完成。",
            "- 入库时同时保留：原始列文本、横排整理文本、断句版、白话版。",
            "",
        ]
    ) + "\n"


def build_review_md(project_id: str, label: str, image_dir: Path, start_page: int, end_page: int) -> str:
    lines = [
        f"# {label}",
        "",
        "## 项目信息",
        "",
        f"- 项目编号：`{project_id}`",
        f"- 页码范围：`{start_page}-{end_page}`",
        f"- JPG 目录： `{image_dir}`",
        "- 校对重点：页顶人物标题、列归属、列顺序、与 SQLite 人物关联。",
        "",
        "## 页面清单",
        "",
    ]
    for page in range(start_page, end_page + 1):
        lines.extend(
            [
                f"### 第{page}页",
                "",
                f"- 原图： `{image_dir / f'page_{page:03d}.jpg'}`",
                "- 标题人物：",
                "- 列顺序是否确认：",
                "- 关联到 persons.id：",
                "- 本页备注：",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    if args.start_page > args.end_page:
        raise SystemExit("--start-page must be <= --end-page")

    project_dir = ROOT / args.project_id
    raw_jpg_dir = project_dir / "raw_jpg"
    ocr_dir = project_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)

    generations = parse_generation_range(args.expected_generations)
    if not args.skip_render:
        render_pages(args.pdf.resolve(), raw_jpg_dir, args.start_page, args.end_page, args.dpi)

    matched_person_count = fetch_person_count(args.db_path.resolve(), generations)
    payload = build_project_payload(
        args.project_id,
        args.label,
        args.pdf.resolve(),
        raw_jpg_dir.resolve(),
        args.start_page,
        args.end_page,
        generations,
        matched_person_count,
    )

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project_dir / "workflow.md").write_text(
        build_workflow_md(args.project_id, args.label, args.start_page, args.end_page, generations),
        encoding="utf-8",
    )
    (project_dir / "review_template.md").write_text(
        build_review_md(args.project_id, args.label, raw_jpg_dir.resolve(), args.start_page, args.end_page),
        encoding="utf-8",
    )
    print(project_dir / "project.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
