#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz
import numpy as np


@dataclass
class ColumnOcr:
    index: int
    x0: int
    x1: int
    width: int
    raw_text: str


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Split a vertical Chinese page into columns and OCR each column.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--page", type=int, required=True, help="1-based page number")
    ap.add_argument("--dpi-scale", type=float, default=3.0)
    ap.add_argument("--threshold", type=int, default=210, help="Dark pixel threshold")
    ap.add_argument("--min-run-width", type=int, default=20)
    ap.add_argument("--min-col-sum-ratio", type=float, default=0.12)
    ap.add_argument("--crop-top", type=float, default=0.12, help="Top crop ratio")
    ap.add_argument("--crop-bottom", type=float, default=0.95, help="Bottom crop ratio")
    ap.add_argument("--pad", type=int, default=20)
    ap.add_argument("--out-dir", type=Path, default=Path("column_ocr_output"))
    ap.add_argument("--frame-threshold", type=int, default=180, help="Threshold for detecting the inner frame")
    ap.add_argument("--frame-pad", type=int, default=18, help="Crop inside the detected frame by this many rendered pixels")
    return ap.parse_args()


def pixmap_to_gray_array(pix: fitz.Pixmap) -> np.ndarray:
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)
    else:
        gray = arr[:, :, 0]
    return gray


def detect_column_runs(gray: np.ndarray, threshold: int, min_run_width: int, ratio: float) -> list[tuple[int, int]]:
    mask = gray < threshold
    col_sum = mask.sum(axis=0)
    smooth = np.convolve(col_sum, np.ones(25) / 25, mode="same")
    thr = max(20, float(smooth.max()) * ratio)

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, value in enumerate(smooth):
        if value >= thr and start is None:
            start = i
        elif value < thr and start is not None:
            if i - start >= min_run_width:
                runs.append((start, i - 1))
            start = None
    if start is not None and len(smooth) - start >= min_run_width:
        runs.append((start, len(smooth) - 1))

    merged: list[tuple[int, int]] = []
    for x0, x1 in runs:
        if not merged:
            merged.append((x0, x1))
            continue
        prev0, prev1 = merged[-1]
        if x0 - prev1 <= 40:
            merged[-1] = (prev0, x1)
        else:
            merged.append((x0, x1))
    return merged


def _best_run(vec: np.ndarray, min_value: float, start: int, end: int) -> tuple[int, int] | None:
    run_start: int | None = None
    best: tuple[int, int] | None = None
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


def run_tesseract(image: Path) -> str:
    cmd = ["tesseract", str(image), "stdout", "-l", "chi_tra_vert", "--psm", "5"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def main() -> int:
    args = parse_args()
    pdf = args.pdf.resolve()
    doc = fitz.open(pdf)
    page = doc.load_page(args.page - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(args.dpi_scale, args.dpi_scale), alpha=False)
    gray = pixmap_to_gray_array(pix)
    frame_left, frame_top, frame_right, frame_bottom = detect_inner_frame(gray, args.frame_threshold)
    x0 = max(0, frame_left + args.frame_pad)
    x1 = min(gray.shape[1], frame_right - args.frame_pad)
    y0 = max(int(gray.shape[0] * args.crop_top), frame_top + args.frame_pad)
    y1 = min(int(gray.shape[0] * args.crop_bottom), frame_bottom - args.frame_pad)
    work = gray[y0:y1, x0:x1]
    runs = detect_column_runs(work, args.threshold, args.min_run_width, args.min_col_sum_ratio)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    page_png = out_dir / f"page_{args.page:03d}.png"
    pix.save(page_png)

    results: list[ColumnOcr] = []
    for idx, (run_x0, run_x1) in enumerate(sorted(runs, key=lambda item: item[0], reverse=True), start=1):
        abs_x0 = x0 + run_x0
        abs_x1 = x0 + run_x1
        clip = fitz.Rect(
            max(0, (abs_x0 - args.pad) / args.dpi_scale),
            max(0, y0 / args.dpi_scale),
            min(pix.width, abs_x1 + args.pad) / args.dpi_scale,
            min(pix.height, y1) / args.dpi_scale,
        )
        col_pix = page.get_pixmap(matrix=fitz.Matrix(args.dpi_scale, args.dpi_scale), clip=clip, alpha=False)
        col_path = out_dir / f"page_{args.page:03d}_col_{idx:02d}.png"
        col_pix.save(col_path)
        raw_text = run_tesseract(col_path)
        results.append(ColumnOcr(index=idx, x0=abs_x0, x1=abs_x1, width=abs_x1 - abs_x0 + 1, raw_text=raw_text))

    json_path = out_dir / f"page_{args.page:03d}_columns.json"
    payload = {
        "frame": {
            "left": x0,
            "top": y0,
            "right": x1,
            "bottom": y1,
        },
        "columns": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
