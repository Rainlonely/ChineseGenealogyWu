#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class OcrPageResult:
    page_number: int
    avg_confidence: float
    confidence_count: int
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a scanned genealogy PDF and OCR it into page-broken Markdown."
    )
    parser.add_argument("pdf", type=Path, help="Input PDF path")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output Markdown path (default: <pdf stem>.ocr.md)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="1-based start page, inclusive",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="1-based end page, inclusive",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=3.0,
        help="Render scale before OCR; 3.0 is a good balance for scanned genealogy pages",
    )
    parser.add_argument(
        "--crop-ratio",
        type=float,
        default=0.06,
        help="Trim white margins on each side before OCR; set 0 to disable",
    )
    parser.add_argument(
        "--lang",
        default="chi_tra_vert+chi_tra",
        help="Tesseract language pack",
    )
    parser.add_argument(
        "--psm",
        type=int,
        default=5,
        help="Tesseract page segmentation mode. 5 works best on this vertical scan sample.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=25.0,
        help="Below this confidence the page is marked for manual review",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N pages",
    )
    return parser.parse_args()


def shell_escape(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_text(text: str) -> str:
    text = shell_escape(text)
    text = text.replace("\x0c", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def page_clip(page: fitz.Page, crop_ratio: float) -> fitz.Rect:
    rect = page.rect
    if crop_ratio <= 0:
        return rect
    dx = rect.width * crop_ratio
    dy = rect.height * crop_ratio
    return fitz.Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 - dx, rect.y1 - dy)


def render_page_image(page: fitz.Page, scale: float, crop_ratio: float, output_png: Path) -> None:
    clip = page_clip(page, crop_ratio)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csGRAY,
        clip=clip,
        alpha=False,
    )
    pix.save(output_png)


def run_tesseract(image_path: Path, lang: str, psm: int) -> tuple[str, float, int]:
    text_cmd = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        lang,
        "--psm",
        str(psm),
    ]
    text_proc = subprocess.run(text_cmd, capture_output=True, text=True, check=True)

    tsv_cmd = text_cmd + ["tsv"]
    tsv_proc = subprocess.run(tsv_cmd, capture_output=True, text=True, check=True)

    confidence_values: list[float] = []
    reader = csv.DictReader(io.StringIO(tsv_proc.stdout), delimiter="\t")
    for row in reader:
        if row.get("level") != "5":
            continue
        raw_conf = row.get("conf", "")
        word = (row.get("text") or "").strip()
        if not word or raw_conf in {"", "-1"}:
            continue
        try:
            conf = float(raw_conf)
        except ValueError:
            continue
        confidence_values.append(conf)

    average = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    return normalize_text(text_proc.stdout), average, len(confidence_values)


def ocr_page(page: fitz.Page, page_number: int, scale: float, crop_ratio: float, lang: str, psm: int) -> OcrPageResult:
    with tempfile.TemporaryDirectory(prefix=f"ocr-page-{page_number:04d}-") as temp_dir:
        image_path = Path(temp_dir) / f"page_{page_number:04d}.png"
        render_page_image(page, scale, crop_ratio, image_path)
        text, avg_conf, count = run_tesseract(image_path, lang, psm)
        return OcrPageResult(
            page_number=page_number,
            avg_confidence=avg_conf,
            confidence_count=count,
            text=text,
        )


def page_review_label(result: OcrPageResult, min_confidence: float) -> str:
    if result.confidence_count == 0:
        return "manual_review_required"
    if result.avg_confidence < min_confidence:
        return "manual_review_recommended"
    return "usable_draft"


def format_page_markdown(result: OcrPageResult, min_confidence: float) -> str:
    review_label = page_review_label(result, min_confidence)
    body = result.text or "[未识别出正文，请人工补录]"
    return (
        f"## 第{result.page_number}页\n\n"
        f"- OCR状态: {review_label}\n"
        f"- 平均置信度: {result.avg_confidence:.2f}\n"
        f"- 参与统计的文字块数: {result.confidence_count}\n\n"
        f"```text\n{body}\n```\n"
        f"\n"
        f"### 关系描述（待校对）\n\n"
        f"```text\n"
        f"[说明]\n"
        f"- 本页若为家谱挂线图，请在此按“父 -> 子”补录关系。\n"
        f"- 同辈、继嗣、过继、配偶、失考等情况，也在此处补注。\n"
        f"\n"
        f"[建议格式]\n"
        f"- 父 -> 子1、子2、子3\n"
        f"- 某人（字某） -> 长子某、次子某\n"
        f"- 某人 配 某氏\n"
        f"- 某人 过继 -> 某支\n"
        f"\n"
        f"[本页关系草稿]\n"
        f"- 待补录\n"
        f"```\n"
    )


def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.exists():
        print(f"Input PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else pdf_path.with_suffix(".ocr.md")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    start_page = max(1, args.start_page)
    end_page = min(page_count, args.end_page or page_count)
    if start_page > end_page:
        print("Invalid page range", file=sys.stderr)
        return 1

    header = [
        f"# {pdf_path.name} OCR 初稿",
        "",
        f"- 源文件: `{pdf_path.name}`",
        f"- 页码范围: 第{start_page}页-第{end_page}页 / 共{page_count}页",
        f"- OCR引擎: `tesseract {args.lang}`",
        f"- 页面模式: `psm {args.psm}`",
        f"- 渲染倍率: `{args.scale}`",
        f"- 裁边比例: `{args.crop_ratio}`",
        "",
        "> 说明：这是机器识别初稿，繁体竖排家谱中的挂线图页请务必人工校对。",
        "",
    ]

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(header))
        for page_number in range(start_page, end_page + 1):
            page = doc.load_page(page_number - 1)
            result = ocr_page(
                page=page,
                page_number=page_number,
                scale=args.scale,
                crop_ratio=args.crop_ratio,
                lang=args.lang,
                psm=args.psm,
            )
            handle.write(format_page_markdown(result, args.min_confidence))
            handle.write("\n")
            if args.progress_every > 0 and (
                page_number == start_page
                or page_number == end_page
                or (page_number - start_page + 1) % args.progress_every == 0
            ):
                print(
                    f"[ocr] page {page_number}/{end_page} avg_conf={result.avg_confidence:.2f}",
                    file=sys.stderr,
                )

    print(f"Wrote Markdown OCR draft to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
