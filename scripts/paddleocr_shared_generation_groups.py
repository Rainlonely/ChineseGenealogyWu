#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import cv2
from paddleocr import PaddleOCR

from paddleocr_group_pages import should_ignore
from reset_group_to_ocr_labels import reset_group_people_from_ocr
from workspace_paths import ROOT

DEFAULT_CONFIG = ROOT / "configs" / "early_generation_groups_001_095.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PaddleOCR once for shared early-generation pages and distribute results to all mapped groups.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to the shared-group config json.")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language")
    parser.add_argument("--max-width", type=int, default=1100, help="Downscale page image to this width before OCR to improve throughput.")
    parser.add_argument(
        "--reset-persons-from-ocr",
        action="store_true",
        help="After distributing OCR text_items, rebuild each group's left-side persons and clear edges.",
    )
    return parser


def prepare_ocr_image(image_path: Path, max_width: int) -> tuple[Path, float]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image: {image_path}")
    height, width = image.shape[:2]
    if width <= max_width:
        return image_path, 1.0
    scale = max_width / width
    resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    temp_dir = ROOT / "data" / "tmp_ocr_shared"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / image_path.name
    cv2.imwrite(str(target), resized)
    return target, scale


def ocr_one_page(ocr: PaddleOCR, image_path: Path, max_width: int) -> tuple[list[dict], list[dict], any]:
    ocr_image_path, scale = prepare_ocr_image(image_path, max_width)
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

    return raw_items, filtered_items, image


def main() -> int:
    args = build_parser().parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    shared_pages_dir = Path(config["shared_pages_dir"]).resolve()
    group_specs = config["groups"]
    unique_pages = sorted({page for group in group_specs for page in group["pages"]})

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    ocr = PaddleOCR(
        lang=args.lang,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )

    groups_state = []
    page_to_groups = {}
    for group in group_specs:
        group_dir = ROOT / group["group_id"]
        group_json_path = group_dir / "group_template.json"
        out_dir = group_dir / "paddleocr_group"
        out_dir.mkdir(parents=True, exist_ok=True)

        data = json.loads(group_json_path.read_text(encoding="utf-8"))
        page_map = {item["page"]: item for item in data.get("pages_data", [])}
        summary = {"pages": []}
        state = {
            "group": group,
            "group_json_path": group_json_path,
            "out_dir": out_dir,
            "data": data,
            "page_map": page_map,
            "summary": summary,
        }
        groups_state.append(state)
        for page in data["pages"]:
            page_to_groups.setdefault(page, []).append(state)

    for page in unique_pages:
        image_path = shared_pages_dir / f"page_{page:03d}.jpg"
        raw_items, filtered_items, annotated = ocr_one_page(ocr, image_path, args.max_width)
        for state in page_to_groups.get(page, []):
            group = state["group"]
            out_dir = state["out_dir"]
            data = state["data"]
            page_map = state["page_map"]
            summary = state["summary"]

            image_path = shared_pages_dir / f"page_{page:03d}.jpg"
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
            cv2.imwrite(str(page_img), annotated)

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
            print(f"{group['group_id']} page {page} done")
            state["group_json_path"].write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (out_dir / "group_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for state in groups_state:
        group_json_path = state["group_json_path"]
        data = state["data"]
        out_dir = state["out_dir"]
        summary = state["summary"]
        group = state["group"]
        if args.reset_persons_from_ocr:
            count = reset_group_people_from_ocr(group_json_path, [int(item) for item in group["generations"]])
            print(f"{group['group_id']}: persons reset from OCR = {count}")
        print(group_json_path)
        print(out_dir / "group_summary.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
