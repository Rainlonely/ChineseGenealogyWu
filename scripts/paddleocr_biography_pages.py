#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from paddleocr import PaddleOCR

try:
    import cv2  # type: ignore
except ModuleNotFoundError:
    cv2 = None


TITLE_IGNORE_CHARS = set("第世姓前後后东東西南北中庄祖租")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PaddleOCR page by page for a biography project.")
    parser.add_argument("--project-json", type=Path, required=True, help="Path to biography project.json")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for per-page OCR outputs")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language")
    parser.add_argument("--page", type=int, action="append", help="Only run selected page numbers")
    parser.add_argument(
        "--title-top-ratio",
        type=float,
        default=0.22,
        help="Top area ratio used to collect title candidates.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=900,
        help="Downscale page image to this width before OCR to improve throughput.",
    )
    return parser


def normalize_poly(poly) -> list[list[float]]:
    if hasattr(poly, "tolist"):
        poly = poly.tolist()
    return [[float(x), float(y)] for x, y in poly]


def normalize_box(box) -> list[float]:
    if hasattr(box, "tolist"):
        box = box.tolist()
    return [float(value) for value in box]


def is_title_candidate(text: str, box: list[float], image_height: int, top_ratio: float, score: float) -> bool:
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 4:
        return False
    if score < 0.45:
        return False
    if any(char in TITLE_IGNORE_CHARS for char in cleaned):
        return False
    top = min(box[1], box[3]) if len(box) >= 4 else 0
    return top <= image_height * top_ratio


def sort_vertical_reading(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            round(item["box"][0] / 10.0) * -1,
            item["box"][1],
        ),
    )


def prepare_ocr_image(image_path: Path, max_width: int) -> tuple[Path, float]:
    if cv2 is None:
        return image_path, 1.0
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Missing page image: {image_path}")
    height, width = image.shape[:2]
    if width <= max_width:
        return image_path, 1.0
    scale = max_width / width
    resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    temp_dir = image_path.parent.parent / "tmp_ocr"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / image_path.name
    cv2.imwrite(str(target), resized)
    return target, scale


def main() -> int:
    args = build_parser().parse_args()
    project_json = args.project_json.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    project = json.loads(project_json.read_text(encoding="utf-8"))
    selected_pages = set(args.page or [])

    ocr = PaddleOCR(
        lang=args.lang,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )

    summary = {"project_id": project.get("project_id"), "pages": []}

    for page_entry in project.get("pages_data", []):
        page_no = int(page_entry["page"])
        if selected_pages and page_no not in selected_pages:
            continue

        image_path = Path(page_entry["image"]).resolve()
        if cv2 is not None:
            image = cv2.imread(str(image_path))
            if image is None:
                raise FileNotFoundError(f"Missing page image: {image_path}")
            image_height = image.shape[0]
        else:
            image = None
            probe = subprocess.run(
                ["sips", "-g", "pixelHeight", str(image_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            image_height = int(probe.stdout.strip().split()[-1])

        ocr_image_path, scale = prepare_ocr_image(image_path, args.max_width)
        result = list(ocr.predict(str(ocr_image_path)))[0]
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
            normalized_poly = normalize_poly(poly)
            normalized_box = normalize_box(box)
            if scale != 1.0:
                normalized_poly = [[point[0] / scale, point[1] / scale] for point in normalized_poly]
                normalized_box = [value / scale for value in normalized_box]
            item = {
                "index": index,
                "text": text,
                "score": float(score),
                "angle": angle,
                "poly": normalized_poly,
                "box": normalized_box,
                "is_title_candidate": is_title_candidate(text, normalized_box, image_height, args.title_top_ratio, float(score)),
            }
            items.append(item)

            if image is not None and cv2 is not None:
                points = [tuple(map(int, point)) for point in normalized_poly]
                color = (0, 0, 255) if item["is_title_candidate"] else (60, 180, 75)
                for point_index in range(len(points)):
                    cv2.line(image, points[point_index], points[(point_index + 1) % len(points)], color, 2)
                x = min(point[0] for point in points)
                y = min(point[1] for point in points)
                cv2.putText(image, str(index), (x, max(20, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 0), 2)

        ordered_items = sort_vertical_reading(items)
        title_candidates = [item for item in ordered_items if item["is_title_candidate"]]

        page_json = out_dir / f"page_{page_no:03d}.paddleocr.json"
        page_txt = out_dir / f"page_{page_no:03d}.paddleocr.txt"
        page_img = out_dir / f"page_{page_no:03d}.paddleocr.annotated.jpg"

        page_json.write_text(
            json.dumps(
                {
                    "page": page_no,
                    "image": str(image_path),
                    "items": items,
                    "ordered_items": ordered_items,
                    "title_candidates": title_candidates,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        page_txt.write_text(
            "\n".join(
                f"{item['index']:02d}\t{item['score']:.4f}\t{'TITLE' if item['is_title_candidate'] else 'TEXT'}\t{item['text']}"
                for item in ordered_items
            )
            + "\n",
            encoding="utf-8",
        )
        if image is not None and cv2 is not None:
            cv2.imwrite(str(page_img), image)

        page_entry["ocr_items"] = ordered_items
        page_entry["title_candidates"] = title_candidates
        page_entry["review_status"] = "ocr_done"
        summary["pages"].append(
            {
                "page": page_no,
                "image": str(image_path),
                "ocr_json": str(page_json),
                "annotated_image": str(page_img) if image is not None and cv2 is not None else None,
                "item_count": len(items),
                "title_candidate_count": len(title_candidates),
            }
        )

    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(project_json)
    print(out_dir / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
