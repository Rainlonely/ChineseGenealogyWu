from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "genealogy.sqlite"


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def print_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("无结果")
        return
    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False, indent=2))


def query_person(conn: sqlite3.Connection, person_id: str | None, name: str | None) -> None:
    clauses = []
    params: list[str] = []
    if person_id:
        clauses.append("p.id = ?")
        params.append(person_id)
    if name:
        clauses.append("(p.name LIKE ? OR p.canonical_name LIKE ?)")
        params.extend([f"%{name}%", f"%{name}%"])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
          p.id,
          p.group_id,
          p.name,
          p.generation,
          p.primary_page_no,
          p.primary_page_image_path,
          p.glyph_asset_path,
          p.root_order,
          p.is_verified,
          p.review_status,
          p.remark,
          COALESCE(tree.tree_status, 'isolated') AS tree_status,
          COALESCE(tree.internal_parent_links, 0) AS internal_parent_links,
          COALESCE(tree.bridge_parent_links, 0) AS bridge_parent_links,
          COALESCE(stats.child_count, 0) AS child_count,
          COALESCE(children.child_ids_json, '[]') AS child_ids_json
        FROM persons AS p
        LEFT JOIN v_person_tree_status AS tree
          ON tree.person_id = p.id
        LEFT JOIN v_person_child_stats AS stats
          ON stats.person_id = p.id
        LEFT JOIN v_person_children_json AS children
          ON children.person_id = p.id
        {where_sql}
        ORDER BY p.generation, p.primary_page_no, p.name
        """,
        params,
    ).fetchall()
    print_rows(rows)


def query_page(conn: sqlite3.Connection, group_id: str, page_no: int) -> None:
    page = conn.execute(
        """
        SELECT group_id, page_no, image_path, page_role, people_locked, keep_generation_axis, manual_notes_json
        FROM pages
        WHERE group_id = ? AND page_no = ?
        """,
        (group_id, page_no),
    ).fetchall()
    people = conn.execute(
        """
        SELECT id, name, generation, is_verified, review_status, remark
        FROM persons
        WHERE group_id = ? AND primary_page_no = ?
        ORDER BY generation, name
        """,
        (group_id, page_no),
    ).fetchall()
    print("页面")
    print_rows(page)
    print("人物")
    print_rows(people)


def query_bridges(conn: sqlite3.Connection, scope_ref: str | None) -> None:
    clauses = ["scope = 'group_bridge'"]
    params: list[str] = []
    if scope_ref:
        clauses.append("scope_ref = ?")
        params.append(scope_ref)
    rows = conn.execute(
        f"""
        SELECT
          id,
          scope_ref,
          parent_person_id,
          child_person_id,
          birth_order_under_parent,
          confidence,
          page_sources_json
        FROM relationships
        WHERE {' AND '.join(clauses)}
        ORDER BY scope_ref, id
        """,
        params,
    ).fetchall()
    print_rows(rows)


def query_missing(conn: sqlite3.Connection, group_id: str) -> None:
    min_generation = conn.execute(
        "SELECT MIN(generation) FROM persons WHERE group_id = ?",
        (group_id,),
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT
          p.id,
          p.name,
          p.generation,
          p.primary_page_no,
          p.primary_page_image_path
        FROM persons AS p
        LEFT JOIN relationships AS r
          ON r.child_person_id = p.id
         AND (r.scope = 'group_internal' AND r.scope_ref = p.group_id)
        WHERE p.group_id = ?
          AND p.generation > ?
          AND r.id IS NULL
        ORDER BY p.primary_page_no, p.generation, p.name
        """,
        (group_id, min_generation),
    ).fetchall()
    print_rows(rows)


def query_completion(conn: sqlite3.Connection, group_id: str | None) -> None:
    clauses = []
    params: list[str] = []
    if group_id:
        clauses.append("group_id = ?")
        params.append(group_id)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
          group_id,
          missing_parent_count,
          cross_group_linked_count,
          non_root_person_count,
          CASE
            WHEN missing_parent_count = 0 THEN 1
            ELSE 0
          END AS group_complete
        FROM v_group_completion
        {where_sql}
        ORDER BY group_id
        """,
        params,
    ).fetchall()
    print_rows(rows)


def query_tree_status(conn: sqlite3.Connection, group_id: str | None, generation: int | None) -> None:
    clauses = []
    params: list[str | int] = []
    if group_id:
        clauses.append("p.group_id = ?")
        params.append(group_id)
    if generation is not None:
        clauses.append("p.generation = ?")
        params.append(generation)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
          p.id,
          p.group_id,
          p.name,
          p.generation,
          p.primary_page_no,
          tree.tree_status,
          tree.internal_parent_links,
          tree.bridge_parent_links,
          tree.child_count
        FROM persons AS p
        LEFT JOIN v_person_tree_status AS tree
          ON tree.person_id = p.id
        {where_sql}
        ORDER BY p.group_id, p.generation, p.primary_page_no, p.name
        """,
        params,
    ).fetchall()
    print_rows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query the genealogy SQLite mirror.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to genealogy.sqlite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    person_parser = subparsers.add_parser("person", help="Query person records")
    person_parser.add_argument("--id", dest="person_id")
    person_parser.add_argument("--name")

    page_parser = subparsers.add_parser("page", help="Query one page and its persons")
    page_parser.add_argument("--group", required=True, dest="group_id")
    page_parser.add_argument("--page", required=True, type=int, dest="page_no")

    bridge_parser = subparsers.add_parser("bridges", help="List cross-group bridge edges")
    bridge_parser.add_argument("--scope-ref")

    missing_parser = subparsers.add_parser("missing", help="List persons still missing a parent inside one group")
    missing_parser.add_argument("--group", required=True, dest="group_id")

    completion_parser = subparsers.add_parser("completion", help="Show group completion and cross-group linkage stats")
    completion_parser.add_argument("--group", dest="group_id")

    tree_parser = subparsers.add_parser("tree-status", help="Show person tree-link status")
    tree_parser.add_argument("--group", dest="group_id")
    tree_parser.add_argument("--generation", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn = connect_db(args.db)
    try:
        if args.command == "person":
            query_person(conn, args.person_id, args.name)
        elif args.command == "page":
            query_page(conn, args.group_id, args.page_no)
        elif args.command == "bridges":
            query_bridges(conn, args.scope_ref)
        elif args.command == "missing":
            query_missing(conn, args.group_id)
        elif args.command == "completion":
            query_completion(conn, args.group_id)
        elif args.command == "tree-status":
            query_tree_status(conn, args.group_id, args.generation)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
