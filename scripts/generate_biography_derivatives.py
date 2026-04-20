#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from import_genealogy_to_sqlite import DEFAULT_DB_PATH


OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
MIMO_CHAT_URL = "https://api.xiaomimimo.com/v1/chat/completions"
DASHSCOPE_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-5"
DEFAULT_MIMO_MODEL = "mimo-v2-flash"
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"


@dataclass
class BiographyRow:
    id: int
    person_id: str
    project_id: str
    source_page_no: int
    source_title_text: str
    source_text_linear: str
    source_text_punctuated: str | None
    source_text_baihua: str | None
    source_text_translation_notes: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate punctuated wenyan text and baihua text for person biographies via an LLM."
    )
    parser.add_argument("--project-id", required=True, help="Biography project id, e.g. bio_001_092_qianbian")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--provider", choices=["auto", "openai", "mimo", "dashscope"], default="auto")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--limit", type=int, default=0, help="Process at most this many rows; 0 means all")
    parser.add_argument("--person-id", default=None, help="Only process one person_id")
    parser.add_argument("--force", action="store_true", help="Re-generate even if punctuated/baihua already look filled")
    parser.add_argument("--dry-run", action="store_true", help="List candidate rows without calling an LLM or updating SQLite")
    parser.add_argument("--sleep-seconds", type=float, default=0.3, help="Sleep between successful calls")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries per row on transient API failure")
    return parser


def choose_provider(explicit: str, *, allow_missing: bool = False) -> str:
    if explicit != "auto":
        return explicit
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("DASHSCOPE_API_KEY"):
        return "dashscope"
    if os.getenv("MIMO_API_KEY"):
        return "mimo"
    if allow_missing:
        return "unresolved"
    raise SystemExit("No LLM credentials found. Set OPENAI_API_KEY or MIMO_API_KEY, or pass --provider with valid credentials.")


def chosen_model(provider: str, override: str | None) -> str:
    if override:
        return override
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    if provider == "dashscope":
        return DEFAULT_DASHSCOPE_MODEL
    return DEFAULT_MIMO_MODEL


def load_rows(conn: sqlite3.Connection, args: argparse.Namespace) -> list[BiographyRow]:
    clauses = [
        "project_id = ?",
        "match_status = 'reviewed_manual'",
        "COALESCE(TRIM(source_text_linear), '') <> ''",
    ]
    params: list[Any] = [args.project_id]
    if args.person_id:
        clauses.append("person_id = ?")
        params.append(args.person_id)
    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT
          id,
          person_id,
          project_id,
          source_page_no,
          COALESCE(source_title_text, person_id) AS source_title_text,
          source_text_linear,
          source_text_punctuated,
          source_text_baihua,
          source_text_translation_notes
        FROM person_biographies
        WHERE {where_sql}
        ORDER BY source_page_no, id
        """,
        params,
    ).fetchall()
    result = [
        BiographyRow(
            id=int(row["id"]),
            person_id=str(row["person_id"]),
            project_id=str(row["project_id"]),
            source_page_no=int(row["source_page_no"]),
            source_title_text=str(row["source_title_text"] or row["person_id"]),
            source_text_linear=str(row["source_text_linear"] or ""),
            source_text_punctuated=row["source_text_punctuated"],
            source_text_baihua=row["source_text_baihua"],
            source_text_translation_notes=row["source_text_translation_notes"],
        )
        for row in rows
    ]
    if not args.force:
        result = [row for row in result if row_needs_generation(row)]
    if args.limit and args.limit > 0:
        result = result[: args.limit]
    return result


def row_needs_generation(row: BiographyRow) -> bool:
    punctuated = (row.source_text_punctuated or "").strip()
    linear = row.source_text_linear.strip()
    baihua = (row.source_text_baihua or "").strip()
    punctuated_missing = not punctuated or punctuated == linear
    baihua_missing = not baihua
    return punctuated_missing or baihua_missing


def build_prompt_parts(row: BiographyRow) -> tuple[str, str]:
    system_text = (
        "你是古籍家谱整理助手。"
        "任务只有两件："
        "第一，把未断句的文言人物小传整理成保留原意的现代中文标点版；"
        "第二，生成忠实、易懂、不夸张的白话文。"
        "必须严格依据原文，不得编造原文没有的信息。"
        "人名、世系、地名、官职、时间、葬地、亲属关系都尽量保留。"
        "若原文含 OCR 疑点，可在 notes 中简短指出，但不要擅自改写为确定事实。"
        "输出必须是 JSON。"
    )
    user_text = (
        f"人物标识: {row.person_id}\n"
        f"人物标题: {row.source_title_text}\n"
        f"来源页: {row.source_page_no}\n"
        "原始横排小传如下，请完成断句和白话：\n"
        f"{row.source_text_linear}"
    )
    return system_text, user_text


def build_messages(row: BiographyRow) -> list[dict[str, Any]]:
    system_text, user_text = build_prompt_parts(row)
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def openai_payload(model: str, row: BiographyRow) -> dict[str, Any]:
    return {
        "model": model,
        "messages": build_messages(row),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "biography_derivatives",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "punctuated_text": {"type": "string"},
                        "baihua_text": {"type": "string"},
                        "translation_notes": {"type": "string"},
                    },
                    "required": ["punctuated_text", "baihua_text", "translation_notes"],
                    "additionalProperties": False,
                },
            },
        },
    }


def mimo_payload(model: str, row: BiographyRow) -> dict[str, Any]:
    system_text, user_text = build_prompt_parts(row)
    user_text = user_text + (
        "\n请严格输出 JSON 对象，格式为 "
        '{"punctuated_text":"...","baihua_text":"...","translation_notes":"..."}。'
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "stream": False,
    }


def dashscope_payload(model: str, row: BiographyRow) -> dict[str, Any]:
    system_text, user_text = build_prompt_parts(row)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "enable_thinking": False,
        "response_format": {"type": "json_object"},
    }


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:1200]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response: {body[:1200]}") from exc


def extract_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Unexpected response payload: {json.dumps(data, ensure_ascii=False)[:1200]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"Unexpected message payload: {json.dumps(message, ensure_ascii=False)[:1200]}")
    return content


def call_llm(provider: str, model: str, row: BiographyRow) -> dict[str, str]:
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        payload = openai_payload(model, row)
        response = post_json(
            OPENAI_CHAT_URL,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload,
        )
        content = extract_message_content(response)
    elif provider == "mimo":
        api_key = os.getenv("MIMO_API_KEY")
        if not api_key:
            raise RuntimeError("MIMO_API_KEY is not set")
        payload = mimo_payload(model, row)
        response = post_json(
            MIMO_CHAT_URL,
            {
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            payload,
        )
        content = extract_message_content(response)
    elif provider == "dashscope":
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not set")
        payload = dashscope_payload(model, row)
        response = post_json(
            DASHSCOPE_CHAT_URL,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload,
        )
        content = extract_message_content(response)
    else:
        raise RuntimeError(f"Unsupported provider: {provider}")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {content[:1000]}") from exc

    punctuated = str(
        parsed.get("punctuated_text")
        or parsed.get("modern_punctuation")
        or parsed.get("parsed_text")
        or parsed.get("punctuated")
        or ""
    ).strip()
    baihua = str(
        parsed.get("baihua_text")
        or parsed.get("plain_chinese_translation")
        or parsed.get("modern_chinese")
        or parsed.get("vernacular_text")
        or parsed.get("plain_chinese")
        or ""
    ).strip()
    raw_notes = (
        parsed.get("translation_notes")
        or parsed.get("notes")
        or parsed.get("note")
        or ""
    )
    if isinstance(raw_notes, list):
        notes = "\n".join(str(item).strip() for item in raw_notes if str(item).strip()).strip()
    else:
        notes = str(raw_notes).strip()
    if not punctuated or not baihua:
        raise RuntimeError(f"Model returned incomplete payload: {json.dumps(parsed, ensure_ascii=False)[:1200]}")
    return {
        "punctuated_text": punctuated,
        "baihua_text": baihua,
        "translation_notes": notes,
    }


def update_row(conn: sqlite3.Connection, row_id: int, generated: dict[str, str]) -> None:
    conn.execute(
        """
        UPDATE person_biographies
        SET
          source_text_punctuated = ?,
          source_text_baihua = ?,
          source_text_translation_notes = ?,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            generated["punctuated_text"],
            generated["baihua_text"],
            generated["translation_notes"] or None,
            row_id,
        ),
    )


def main() -> int:
    args = build_parser().parse_args()
    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        rows = load_rows(conn, args)
        provider = choose_provider(args.provider, allow_missing=args.dry_run)
        model = chosen_model(provider if provider != "unresolved" else "openai", args.model)
        if args.dry_run:
            print(f"provider={provider}")
            print(f"model={model}")
            print(f"candidate_rows={len(rows)}")
            for row in rows[:10]:
                print(
                    f"- id={row.id} page={row.source_page_no} person_id={row.person_id} title={row.source_title_text}"
                )
            if len(rows) > 10:
                print(f"... truncated {len(rows) - 10} more rows")
            return 0
        if not rows:
            print("candidate_rows=0")
            return 0

        processed = 0
        failures = 0
        started_at = time.time()
        for index, row in enumerate(rows, start=1):
            last_error: str | None = None
            for attempt in range(1, args.max_retries + 1):
                try:
                    generated = call_llm(provider, model, row)
                    update_row(conn, row.id, generated)
                    conn.commit()
                    processed += 1
                    print(
                        f"[ok] {index}/{len(rows)} id={row.id} person_id={row.person_id} page={row.source_page_no}",
                        flush=True,
                    )
                    time.sleep(max(0.0, args.sleep_seconds))
                    last_error = None
                    break
                except Exception as exc:  # pragma: no cover - network and model variability
                    last_error = str(exc)
                    if attempt >= args.max_retries:
                        failures += 1
                        print(
                            f"[fail] {index}/{len(rows)} id={row.id} person_id={row.person_id} error={last_error}",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        sleep_for = min(6.0, 1.5 * attempt)
                        time.sleep(sleep_for)
            if last_error and args.max_retries <= 0:
                failures += 1

        elapsed = time.time() - started_at
        print(f"provider={provider}")
        print(f"model={model}")
        print(f"processed={processed}")
        print(f"failures={failures}")
        print(f"elapsed_seconds={elapsed:.1f}")
        return 0 if failures == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
