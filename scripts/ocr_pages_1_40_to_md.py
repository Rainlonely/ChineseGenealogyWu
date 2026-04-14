#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import fitz
import numpy as np


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="OCR pages into one Markdown file.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--end-page", type=int, default=40)
    ap.add_argument("--image-dir", type=Path, default=Path("pages_jpg_001_040"))
    ap.add_argument("--output", type=Path, default=Path("pages_001_040.md"))
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--frame-threshold", type=int, default=180)
    ap.add_argument("--frame-pad", type=int, default=18)
    return ap.parse_args()


def pixmap_to_gray_array(pix: fitz.Pixmap) -> np.ndarray:
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        return (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)
    return arr[:, :, 0]


def _best_run(vec: np.ndarray, min_value: float, start: int, end: int) -> tuple[int, int] | None:
    run_start = None
    best = None
    best_score = -1.0
    for i in range(start, end):
        if vec[i] >= min_value and run_start is None:
            run_start = i
        elif (vec[i] < min_value or i == end - 1) and run_start is not None:
            run_end = i if vec[i] >= min_value and i == end - 1 else i - 1
            score = float(vec[run_start:run_end + 1].sum())
            if score > best_score:
                best_score = score
                best = (run_start, run_end)
            run_start = None
    return best


def detect_inner_frame(gray: np.ndarray, threshold: int) -> tuple[int, int, int, int]:
    mask = gray < threshold
    row_sum = mask.sum(axis=1)
    col_sum = mask.sum(axis=0)
    h, w = gray.shape
    row_min = max(50, int(w * 0.35))
    col_min = max(50, int(h * 0.35))
    top_run = _best_run(row_sum, row_min, 0, h // 3)
    bottom_run = _best_run(row_sum, row_min, (h * 2) // 3, h)
    left_run = _best_run(col_sum, col_min, 0, w // 3)
    right_run = _best_run(col_sum, col_min, (w * 2) // 3, w)
    if not (top_run and bottom_run and left_run and right_run):
        return (0, 0, w, h)
    top = top_run[1]
    bottom = bottom_run[0]
    left = left_run[1]
    right = right_run[0]
    return (left, top, right, bottom)


def detect_vertical_splits(gray: np.ndarray) -> list[tuple[int, int]]:
    mask = gray < 210
    col_sum = mask.sum(axis=0)
    smooth = np.convolve(col_sum, np.ones(25) / 25, mode="same")
    thr = max(20.0, float(smooth.max()) * 0.12)
    runs: list[tuple[int, int]] = []
    start = None
    for i, val in enumerate(smooth):
        if val >= thr and start is None:
            start = i
        elif val < thr and start is not None:
            if i - start >= 20:
                runs.append((start, i - 1))
            start = None
    if start is not None and len(smooth) - start >= 20:
        runs.append((start, len(smooth) - 1))
    merged: list[tuple[int, int]] = []
    for x0, x1 in runs:
        if not merged:
            merged.append((x0, x1))
        else:
            px0, px1 = merged[-1]
            if x0 - px1 <= 40:
                merged[-1] = (px0, x1)
            else:
                merged.append((x0, x1))
    return sorted(merged, key=lambda item: item[0], reverse=True)


def run_tesseract(image_path: Path, psm: int = 5) -> str:
    proc = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", "chi_tra_vert", "--psm", str(psm)],
        capture_output=True,
        text=True,
        check=True,
    )
    text = proc.stdout.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def ocr_page(page: fitz.Page, image_path: Path, scale: float, frame_threshold: int, frame_pad: int) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    gray = pixmap_to_gray_array(pix)
    left, top, right, bottom = detect_inner_frame(gray, frame_threshold)
    left = max(0, left + frame_pad)
    top = max(0, top + frame_pad)
    right = min(gray.shape[1], right - frame_pad)
    bottom = min(gray.shape[0], bottom - frame_pad)
    inner = gray[top:bottom, left:right]
    runs = detect_vertical_splits(inner)

    # If splitting fails, OCR the whole inner frame.
    if len(runs) <= 1:
        clip = fitz.Rect(left / scale, top / scale, right / scale, bottom / scale)
        temp_img = image_path.parent / f"{image_path.stem}.inner.png"
        page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False).save(temp_img)
        return run_tesseract(temp_img)

    parts: list[str] = []
    for idx, (x0, x1) in enumerate(runs, start=1):
        abs_x0 = left + x0
        abs_x1 = left + x1
        clip = fitz.Rect(max(0, (abs_x0 - 20) / scale), top / scale, min(gray.shape[1], abs_x1 + 20) / scale, bottom / scale)
        col_img = image_path.parent / f"{image_path.stem}.col{idx:02d}.png"
        page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False).save(col_img)
        txt = run_tesseract(col_img)
        if txt:
            parts.append(txt.replace("\n", " "))
    return "\n".join(parts).strip()


def main() -> int:
    args = parse_args()
    pdf = args.pdf.resolve()
    image_dir = args.image_dir.resolve()
    image_dir.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()

    doc = fitz.open(pdf)
    with output.open("w", encoding="utf-8") as handle:
        handle.write(f"# 第{args.start_page}页至第{args.end_page}页\n\n")
        for page_num in range(args.start_page, args.end_page + 1):
            img_path = image_dir / f"page_{page_num:03d}.jpg"
            if not img_path.exists():
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(matrix=fitz.Matrix(args.scale, args.scale), alpha=False)
                pix.save(str(img_path), output="jpeg")
            page = doc.load_page(page_num - 1)
            text = ocr_page(page, img_path, args.scale, args.frame_threshold, args.frame_pad)
            handle.write(f"## 第{page_num}页\n\n")
            handle.write(f"原图： [{img_path.name}]({img_path.resolve()})\n\n")
            handle.write("人工校验顺序文本：\n\n")
            handle.write("```text\n")
            handle.write((text or "") + "\n")
            handle.write("```\n\n")
            print(f"[ocr] page {page_num}/{args.end_page}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
