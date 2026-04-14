#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import cv2
from paddleocr import PaddleOCR

from reset_group_to_ocr_labels import reset_group_people_from_ocr


IGNORE_PATTERNS = [
    r"^\s*$",
    r"^[一二三四五六七八九十百零〇0-9]+子$",
    r"^[一二三四五六七八九十百零〇0-9]+$",
    r"^止$",
    r"^[一二三四五六七八九十百零〇0-9]+世$",
    r".*公支$",
    r"^全圖$",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PaddleOCR across genealogy group pages and store filtered text boxes.")
    parser.add_argument("--group-json", type=Path, required=True, help="Path to group_template.json")
    parser.add_argument("--images-dir", type=Path, required=True, help="Directory with cropped page images")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for PaddleOCR outputs")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language")
    parser.add_argument("--max-width", type=int, default=0, help="Downscale page image to this width before OCR; 0 disables downscaling.")
    parser.add_argument("--mobile-model", action="store_true", help="Use PaddleOCR mobile detection/recognition models for faster batch initialization.")
    parser.add_argument(
        "--reset-persons-from-ocr",
        action="store_true",
        help="After OCR finishes, rebuild left-side persons from cleaned OCR labels and clear edges.",
    )
    return parser


def should_ignore(text: str) -> bool:
    cleaned = text.strip()
    return any(re.fullmatch(pattern, cleaned) for pattern in IGNORE_PATTERNS)


def prepare_ocr_image(image_path: Path, max_width: int, temp_dir: Path) -> tuple[Path, float]:
    if max_width <= 0:
        return image_path, 1.0
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image: {image_path}")
    height, width = image.shape[:2]
    if width <= max_width:
        return image_path, 1.0
    scale = max_width / width
    resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / image_path.name
    cv2.imwrite(str(target), resized)
    return target, scale


def main() -> int:
    args = build_parser().parse_args()
    group_json = args.group_json.resolve()
    images_dir = args.images_dir.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    data = json.loads(group_json.read_text(encoding="utf-8"))
    page_map = {item["page"]: item for item in data.get("pages_data", [])}
    ocr_kwargs = {
        "lang": args.lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": True,
    }
    if args.mobile_model:
        ocr_kwargs.update(
            {
                "text_detection_model_name": "PP-OCRv5_mobile_det",
                "text_recognition_model_name": "PP-OCRv5_mobile_rec",
            }
        )
    ocr = PaddleOCR(**ocr_kwargs)

    summary = {"pages": []}

    for page in data["pages"]:
        image_path = images_dir / f"page_{page:03d}.jpg"
        ocr_image_path, scale = prepare_ocr_image(image_path, args.max_width, out_dir.parent / "tmp_ocr")
        result = list(ocr.predict(str(ocr_image_path)))[0]
        raw_items = []
        filtered_items = []

        image = cv2.imread(str(image_path))

        for index, (text, score, poly, angle, box) in enumerate(
            zip(
                result["rec_texts"],
                result["rec_scores"],
                result["dt_polys"],
                result["textline_orientation_angles"],
                result["rec_boxes"],
            )
        ):
            item = {
                "index": index,
                "text": text,
                "score": float(score),
                "angle": angle,
                "poly": [
                    [int(round(point[0] / scale)), int(round(point[1] / scale))]
                    for point in (poly.tolist() if hasattr(poly, "tolist") else poly)
                ],
                "box": [int(round(value / scale)) for value in (box.tolist() if hasattr(box, "tolist") else box)],
                "ignored": should_ignore(text),
            }
            raw_items.append(item)
            if not item["ignored"]:
                filtered_items.append(item)

            points = [tuple(map(int, point)) for point in item["poly"]]
            color = (120, 120, 120) if item["ignored"] else (0, 0, 255)
            for point_index in range(len(points)):
                cv2.line(image, points[point_index], points[(point_index + 1) % len(points)], color, 2)
            x = min(point[0] for point in points)
            y = min(point[1] for point in points)
            cv2.putText(
                image,
                str(index),
                (x, max(20, y - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 0, 0),
                2,
            )

        page_json = out_dir / f"page_{page:03d}.paddleocr.json"
        page_txt = out_dir / f"page_{page:03d}.paddleocr.txt"
        page_img = out_dir / f"page_{page:03d}.paddleocr.annotated.jpg"

        page_json.write_text(
            json.dumps(
                {
                    "page": page,
                    "image": str(image_path),
                    "raw_count": len(raw_items),
                    "filtered_count": len(filtered_items),
                    "items": raw_items,
                    "filtered_items": filtered_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        page_txt.write_text(
            "\n".join(
                f"{item['index']:02d}\t{item['score']:.4f}\t{'IGN' if item['ignored'] else 'TXT'}\t{item['text']}"
                for item in raw_items
            ),
            encoding="utf-8",
        )
        cv2.imwrite(str(page_img), image)

        if page in page_map:
            page_map[page]["text_items"] = filtered_items

        summary["pages"].append(
            {
                "page": page,
                "image": str(image_path),
                "raw_count": len(raw_items),
                "filtered_count": len(filtered_items),
                "annotated_image": str(page_img),
                "json": str(page_json),
            }
        )

    group_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "group_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.reset_persons_from_ocr:
        default_hints = data.get("generations") or next(
            (item.get("generation_hint") for item in data.get("pages_data", []) if item.get("generation_hint")),
            [],
        )
        count = reset_group_people_from_ocr(group_json, [int(item) for item in default_hints])
        print(f"persons reset from OCR: {count}")
    print(group_json)
    print(out_dir / "group_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
