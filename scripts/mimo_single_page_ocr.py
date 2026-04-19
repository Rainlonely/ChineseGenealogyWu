#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

import requests


XIAOMI_CHAT_URL = "https://api.xiaomimimo.com/v1/chat/completions"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run a single page OCR test with Xiaomi Mimo.")
    ap.add_argument("image", type=Path, help="Input page image, e.g. page_011.png")
    ap.add_argument(
        "--model",
        default="mimo-v2-flash",
        help="Mimo model name",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output markdown/json path",
    )
    return ap.parse_args()


def image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{raw}"


def main() -> int:
    args = parse_args()
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise SystemExit("MIMO_API_KEY is not set")

    image_path = args.image.expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    prompt = (
        "你是古籍与家谱 OCR 专家。请只做 OCR 转写，不要翻译，不要解释。"
        "这是一页中文古代文献扫描图，文字方向是从上到下、从右到左。"
        "请尽量保留原始版式顺序。"
        "如果是目录页，请按右到左的列顺序输出。"
        "如果遇到不确定的字，用 [?] 标注。"
        "输出严格 JSON，格式为 "
        "{\"page_type\":\"...\",\"reading_order\":\"top-to-bottom,right-to-left\","
        "\"ocr_text\":\"...\",\"notes\":[\"...\"]}。"
    )

    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    resp = requests.post(XIAOMI_CHAT_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code >= 400:
        raise SystemExit(f"Mimo API error {resp.status_code}: {resp.text[:1200]}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise SystemExit(f"Unexpected response: {json.dumps(data, ensure_ascii=False)[:1200]}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise SystemExit(f"Unexpected message content: {json.dumps(message, ensure_ascii=False)[:1200]}")

    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
