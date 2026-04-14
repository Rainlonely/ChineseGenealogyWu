#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workspace_paths import ROOT

DEFAULT_CONFIG = ROOT / "configs" / "early_generation_groups_001_095.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare early generation workspaces that share existing page JPG assets.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="JSON config describing shared early-generation groups.")
    return parser


def build_review_template(group_id: str, label: str, generations: list[int], pages: list[int], shared_pages_dir: Path) -> str:
    lines = [
        f"# {label}",
        "",
        "## 组信息",
        "",
        f"- 组编号：`{group_id}`",
        f"- 世次范围：`{generations[0]}-{generations[-1]}世`",
        f"- 共享页码：`{','.join(map(str, pages))}`",
        f"- 共享 JPG 目录： `{shared_pages_dir}`",
        "",
        "## 处理原则",
        "",
        "- 早期世代按共享页资源工作，不重复渲染 JPG。",
        "- 不同五世组允许引用同一页图片。",
        "- 后续 OCR、人物初始化、补链都在各自 group_template.json 内独立进行。",
        "",
        "## 页面清单",
        "",
    ]
    for page in pages:
        lines.extend(
            [
                f"### 第{page}页",
                "",
                f"- JPG： `{shared_pages_dir / f'page_{page:03d}.jpg'}`",
                "- 本页备注：",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def build_group_template(group_id: str, label: str, generations: list[int], pages: list[int], pdf_path: str, shared_pages_dir: Path) -> dict:
    shared_dir_name = shared_pages_dir.name
    return {
        "group_id": group_id,
        "label": label,
        "pages": pages,
        "source_pdf": pdf_path,
        "raw_images_dir": str(shared_pages_dir),
        "cropped_images_dir": str(shared_pages_dir),
        "notes": [
            "本组使用共享 JPG 页资源，不重复渲染页面。",
            "由于早期世代存在跨组共用页，pages_data.image 直接引用共享页路径。",
            "人物初始化与补链仍按单组进行。",
        ],
        "page_index_rule": {
            "group_title_page": pages[0],
            "structure_pages": pages,
            "generation_axis_pages": [pages[0]],
            "shared_page_pool": True,
            "crop_policy": "reuse_existing_shared_jpg",
        },
        "generations": generations,
        "persons": [],
        "edges": [],
        "pages_data": [
            {
                "page": page,
                "image": f"/{shared_dir_name}/page_{page:03d}.jpg",
                "generation_hint": generations,
                "text_items": [],
                "line_items": [],
                "raw_markers": [],
                "manual_notes": [],
                "people_locked": False,
                "page_role": "group_title_page+structure_page" if index == 0 else "structure_page",
                "keep_generation_axis": index == 0,
            }
            for index, page in enumerate(pages)
        ],
    }


def main() -> int:
    args = build_parser().parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    shared_pages_dir = Path(config["shared_pages_dir"])
    for page in {page for group in config["groups"] for page in group["pages"]}:
        page_path = shared_pages_dir / f"page_{page:03d}.jpg"
        if not page_path.exists():
            raise FileNotFoundError(f"Missing shared page JPG: {page_path}")

    for group in config["groups"]:
        out_dir = ROOT / group["group_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        group_template = build_group_template(
            group["group_id"],
            group["label"],
            group["generations"],
            group["pages"],
            config["pdf_path"],
            shared_pages_dir,
        )
        (out_dir / "group_template.json").write_text(
            json.dumps(group_template, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (out_dir / "workflow.md").write_text(
            "\n".join(
                [
                    f"# {group['group_id']} Workflow",
                    "",
                    f"- Shared Pages: `{','.join(map(str, group['pages']))}`",
                    f"- Generations: `{','.join(map(str, group['generations']))}`",
                    "- Stage 1: OCR boxes and people initialization",
                    "- Stage 2: Manual image-side binding and graph linking",
                    "- Asset strategy: reuse shared JPG pages from pages_jpg_001_040",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (out_dir / "review_template.md").write_text(
            build_review_template(
                group["group_id"],
                group["label"],
                group["generations"],
                group["pages"],
                shared_pages_dir,
            ),
            encoding="utf-8",
        )
        (out_dir / "paddleocr_group").mkdir(exist_ok=True)
        print(out_dir / "group_template.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
