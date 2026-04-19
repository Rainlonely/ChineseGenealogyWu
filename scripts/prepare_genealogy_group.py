#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - local env fallback
    fitz = None

try:
    import pypdfium2 as pdfium
except ModuleNotFoundError:  # pragma: no cover - local env fallback
    pdfium = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a genealogy group: render raw JPGs, crop pages, and initialize group_template.json.")
    parser.add_argument("--pdf", type=Path, required=True, help="Source PDF path")
    parser.add_argument("--out-dir", type=Path, required=True, help="Target group directory, e.g. gen_098_102")
    parser.add_argument("--page-start", type=int, required=True, help="1-based start page")
    parser.add_argument("--page-end", type=int, required=True, help="1-based end page")
    parser.add_argument("--generations", required=True, help="Comma separated generation hints, e.g. 98,99,100,101,102")
    parser.add_argument("--label", help="Optional human-readable group label")
    parser.add_argument("--dpi", type=int, default=220, help="Render DPI")
    return parser


def detect_crop_box(image_path: Path, preserve_right_extra: bool = False) -> tuple[int, int, int, int]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
      raise RuntimeError(f"Failed to read image: {image_path}")
    height, width = image.shape[:2]
    mask = image < 242
    ys, xs = mask.nonzero()
    if len(xs) == 0 or len(ys) == 0:
        return 0, 0, width, height
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    pad_x = max(18, int(width * 0.012))
    pad_y = max(18, int(height * 0.012))
    left = max(0, x0 - pad_x)
    top = max(0, y0 - pad_y)
    right = min(width, x1 + pad_x + (90 if preserve_right_extra else 24))
    bottom = min(height, y1 + pad_y)
    return left, top, right, bottom


def build_review_template(out_dir: Path, page_start: int, page_end: int, generations: list[int], label: str) -> str:
    lines = [
        f"# {label}",
        "",
        "## 组信息",
        "",
        f"- 组编号：`{out_dir.name}`",
        f"- 对应页码：`{page_start}-{page_end}`",
        f"- 世次范围：`{','.join(map(str, generations))}`",
        f"- 原始图片目录： `{out_dir / 'raw_jpg'}`",
        f"- 自动裁切目录： `{out_dir / 'cropped_jpg'}`",
        "",
        "## 处理原则",
        "",
        "- 以五世作为一个整体处理，不按单页孤立解释。",
        "- 第一页默认保留完整世代标尺，作为 `generation_axis` 参考页。",
        "- OCR 阶段保留辅助标记，不直接进入最终人物主数据。",
        "- 最终结构化数据只保留人物节点与父子边。",
        "",
        "## 页面清单",
        "",
    ]
    for page_no in range(page_start, page_end + 1):
        lines.extend(
            [
                f"### 第{page_no}页",
                "",
                f"- 原图： `{out_dir / 'raw_jpg' / f'page_{page_no:03d}.jpg'}`",
                f"- 裁切图： `{out_dir / 'cropped_jpg' / f'page_{page_no:03d}.jpg'}`",
                "- 本页备注：",
                "",
            ]
        )
    lines.extend(
        [
            "## 结构抽取记录",
            "",
            "### 人物节点",
            "",
            "```text",
            "待整理",
            "```",
            "",
            "### 父子关系",
            "",
            "```text",
            "待整理",
            "```",
            "",
            "### 辅助标记",
            "",
            "```text",
            "待整理",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_page_to_jpg(pdf_path: Path, page_no: int, dpi: int, raw_path: Path) -> None:
    if fitz is not None:
        doc = fitz.open(pdf_path)
        try:
            scale = dpi / 72.0
            matrix = fitz.Matrix(scale, scale)
            page = doc.load_page(page_no - 1)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(str(raw_path))
        finally:
            doc.close()
        return
    if pdfium is not None:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            page = pdf.get_page(page_no - 1)
            try:
                bitmap = page.render(scale=dpi / 72.0)
                bitmap.to_pil().save(str(raw_path), format="JPEG")
            finally:
                page.close()
        finally:
            pdf.close()
        return
    raise RuntimeError("Neither fitz nor pypdfium2 is available for PDF rendering.")


def main() -> int:
    args = build_parser().parse_args()
    pdf_path = args.pdf.resolve()
    out_dir = args.out_dir.resolve()
    raw_dir = out_dir / "raw_jpg"
    cropped_dir = out_dir / "cropped_jpg"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cropped_dir.mkdir(parents=True, exist_ok=True)

    generations = [int(item.strip()) for item in args.generations.split(",") if item.strip()]
    pages = list(range(args.page_start, args.page_end + 1))
    label = args.label or f"{generations[0]}-{generations[-1]}世"

    for page_no in pages:
        raw_path = raw_dir / f"page_{page_no:03d}.jpg"
        render_page_to_jpg(pdf_path, page_no, args.dpi, raw_path)

        image = cv2.imread(str(raw_path))
        left, top, right, bottom = detect_crop_box(raw_path, preserve_right_extra=(page_no == args.page_start))
        cropped = image[top:bottom, left:right]
        cropped_path = cropped_dir / f"page_{page_no:03d}.jpg"
        cv2.imwrite(str(cropped_path), cropped)

    group_template = {
        "group_id": out_dir.name,
        "label": label,
        "pages": pages,
        "source_pdf": str(pdf_path),
        "raw_images_dir": str(raw_dir),
        "cropped_images_dir": str(cropped_dir),
        "notes": [
            "本组按五世为一组处理。",
            "第一页同时作为 group_title_page 与 structure_page。",
            "裁切规则以保全结构为优先：宁可多留边缘噪音，也不裁掉任何名字、线头、X子、止。",
            "OCR 辅助标记保留在识别层，不直接进入最终人物主数据。",
        ],
        "page_index_rule": {
            "group_title_page": args.page_start,
            "structure_pages": pages,
            "generation_axis_pages": [args.page_start],
            "right_branch_labels_kept_pages": [],
            "other_pages_inherit_group_context": True,
            "crop_policy": "safe_preserve_structure",
        },
        "generations": generations,
        "persons": [],
        "edges": [],
        "pages_data": [
            {
                "page": page_no,
                "image": f"/{out_dir.name}/cropped_jpg/page_{page_no:03d}.jpg",
                "generation_hint": generations,
                "text_items": [],
                "line_items": [],
                "raw_markers": [],
                "manual_notes": [],
                "page_role": "group_title_page+structure_page" if page_no == args.page_start else "structure_page",
                "keep_generation_axis": page_no == args.page_start,
            }
            for page_no in pages
        ],
    }
    (out_dir / "group_template.json").write_text(json.dumps(group_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "workflow.md").write_text(
        "\n".join(
            [
                f"# {out_dir.name} Workflow",
                "",
                f"- Pages: `{args.page_start}-{args.page_end}`",
                f"- Generations: `{','.join(map(str, generations))}`",
                "- Stage 1: OCR boxes and people initialization",
                "- Stage 2: Manual image-side binding and graph linking",
                "- Sibling order rule: right to left means elder to younger",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (out_dir / "review_template.md").write_text(
        build_review_template(out_dir, args.page_start, args.page_end, generations, label),
        encoding="utf-8",
    )
    print(out_dir / "group_template.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
