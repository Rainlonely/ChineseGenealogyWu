#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR


OCR = None


def get_ocr():
    global OCR
    if OCR is None:
        OCR = PaddleOCR(lang="ch")
    return OCR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR a single genealogy name image or crop.")
    parser.add_argument("--image", required=True, help="Source image path")
    parser.add_argument("--box", help="Optional crop box as JSON [x1,y1,x2,y2]")
    parser.add_argument("--padding", type=int, default=24)
    return parser.parse_args()


def crop_image(image_path: Path, box_json: str | None, padding: int) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    if not box_json:
        return image
    box = json.loads(box_json)
    x1 = max(0, int(box[0]) - padding)
    y1 = max(0, int(box[1]) - padding)
    x2 = min(image.width, int(box[2]) + padding)
    y2 = min(image.height, int(box[3]) + padding)
    return image.crop((x1, y1, x2, y2))


def image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def main() -> int:
    args = parse_args()
    image_path = Path(args.image)
    crop = crop_image(image_path, args.box, args.padding)
    result = get_ocr().ocr(np.array(crop))
    lines = []
    for page_result in result or []:
        if isinstance(page_result, dict):
            texts = page_result.get("rec_texts") or []
            scores = page_result.get("rec_scores") or []
            for index, text in enumerate(texts):
                cleaned = str(text or "").strip()
                if not cleaned:
                    continue
                score = float(scores[index] or 0) if index < len(scores) else 0.0
                lines.append({"text": cleaned, "score": score})
            continue
        for item in page_result or []:
            if not item or len(item) < 2:
                continue
            text = str(item[1][0] or "").strip()
            score = float(item[1][1] or 0)
            if not text:
                continue
            lines.append({"text": text, "score": score})
    joined = "".join(line["text"] for line in lines)
    candidates = []
    if joined:
        candidates.append(joined)
    for line in sorted(lines, key=lambda item: item["score"], reverse=True):
        if line["text"] not in candidates:
            candidates.append(line["text"])
    print(json.dumps({
        "ok": True,
        "crop_image": image_to_data_url(crop),
        "lines": lines,
        "candidates": candidates,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
