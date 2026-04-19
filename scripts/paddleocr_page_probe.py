#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import cv2
from paddleocr import PaddleOCR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PaddleOCR on a single page image and save probe outputs.")
    parser.add_argument("image", type=Path, help="Input page image path.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("paddleocr_test"),
        help="Output directory for annotated image and JSON.",
    )
    parser.add_argument("--lang", default="ch", help="PaddleOCR language.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    image_path = args.image.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    ocr = PaddleOCR(
        lang=args.lang,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )
    result = list(ocr.predict(str(image_path)))[0]

    items = []
    for index, (text, score, poly, angle, box) in enumerate(
        zip(
            result["rec_texts"],
            result["rec_scores"],
            result["dt_polys"],
            result["textline_orientation_angles"],
            result["rec_boxes"],
        )
    ):
        items.append(
            {
                "index": index,
                "text": text,
                "score": float(score),
                "angle": angle,
                "poly": poly.tolist() if hasattr(poly, "tolist") else poly,
                "box": box.tolist() if hasattr(box, "tolist") else box,
            }
        )

    image = cv2.imread(str(image_path))
    for item in items:
        points = [tuple(map(int, point)) for point in item["poly"]]
        for idx in range(len(points)):
            cv2.line(image, points[idx], points[(idx + 1) % len(points)], (0, 0, 255), 2)
        x = min(point[0] for point in points)
        y = min(point[1] for point in points)
        cv2.putText(
            image,
            str(item["index"]),
            (x, max(20, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 0),
            2,
        )

    stem = image_path.stem
    json_path = out_dir / f"{stem}.paddleocr.json"
    annotated_path = out_dir / f"{stem}.paddleocr.annotated.jpg"
    text_path = out_dir / f"{stem}.paddleocr.txt"

    json_path.write_text(
        json.dumps({"image": str(image_path), "count": len(items), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text_path.write_text(
        "\n".join(f"{item['index']:02d}\t{item['score']:.4f}\t{item['text']}" for item in items),
        encoding="utf-8",
    )
    cv2.imwrite(str(annotated_path), image)

    print(json_path)
    print(annotated_path)
    print(text_path)
    print(f"count={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
