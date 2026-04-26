from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.connection import connect


class HistoryRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def resolve_person_id(self, person_ref: str) -> Optional[str]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT p.id
                FROM persons AS p
                WHERE p.id = ? OR p.source_person_id = ?
                ORDER BY CASE WHEN p.id = ? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (person_ref, person_ref, person_ref),
            ).fetchone()
            return str(row["id"]) if row else None
        finally:
            conn.close()

    def search_persons(self, query: str, limit: int, generation: Optional[int] = None) -> List[Dict[str, Any]]:
        search_like = f"%{query}%"
        generation_filter = "AND p.generation = ?" if generation is not None else ""
        conn = connect(self.db_path)
        try:
            primary_rows = conn.execute(
                f"""
                SELECT
                  p.id,
                  p.source_person_id,
                  p.name,
                  p.generation,
                  p.glyph_asset_path,
                  p.glyph_asset_oss_key,
                  (
                    SELECT fp.name
                    FROM relationships AS r
                    JOIN persons AS fp
                      ON fp.id = r.parent_person_id
                    WHERE r.child_person_id = p.id
                    ORDER BY r.id
                    LIMIT 1
                  ) AS father_name,
                  EXISTS (
                    SELECT 1 FROM person_biographies AS pb WHERE pb.person_id = p.id
                  ) AS has_biography,
                  EXISTS (
                    SELECT 1 FROM lineage_attachments AS la
                    WHERE la.historical_person_ref = p.id
                      AND la.status = 'active'
                  ) AS has_modern_extension
                  ,
                  CASE
                    WHEN p.name = ? OR COALESCE(p.canonical_name, '') = ? THEN 'primary_exact'
                    ELSE 'primary_fuzzy'
                  END AS match_type,
                  CASE
                    WHEN p.name = ? THEN p.name
                    WHEN COALESCE(p.canonical_name, '') = ? THEN p.canonical_name
                    ELSE p.name
                  END AS matched_name
                FROM persons AS p
                WHERE (p.name LIKE ? OR COALESCE(p.canonical_name, '') LIKE ?)
                  {generation_filter}
                ORDER BY
                  CASE WHEN p.name = ? THEN 0 ELSE 1 END,
                  p.generation,
                  p.primary_page_no,
                  p.name
                LIMIT ?
                """,
                (
                    query,
                    query,
                    query,
                    query,
                    search_like,
                    search_like,
                    *([generation] if generation is not None else []),
                    query,
                    limit,
                ),
            ).fetchall()
            alias_rows = conn.execute(
                f"""
                SELECT
                  p.id,
                  p.source_person_id,
                  p.name,
                  p.generation,
                  p.glyph_asset_path,
                  p.glyph_asset_oss_key,
                  (
                    SELECT fp.name
                    FROM relationships AS r
                    JOIN persons AS fp
                      ON fp.id = r.parent_person_id
                    WHERE r.child_person_id = p.id
                    ORDER BY r.id
                    LIMIT 1
                  ) AS father_name,
                  EXISTS (
                    SELECT 1 FROM person_biographies AS pb WHERE pb.person_id = p.id
                  ) AS has_biography,
                  EXISTS (
                    SELECT 1 FROM lineage_attachments AS la
                    WHERE la.historical_person_ref = p.id
                      AND la.status = 'active'
                  ) AS has_modern_extension,
                  CASE
                    WHEN psa.alias_text = ? THEN 'alias_exact'
                    ELSE 'alias_fuzzy'
                  END AS match_type,
                  psa.alias_text AS matched_name
                FROM person_search_aliases AS psa
                JOIN persons AS p
                  ON p.id = psa.person_ref
                WHERE psa.person_source = 'historical'
                  AND psa.status = 'active'
                  AND psa.alias_text LIKE ?
                  {generation_filter}
                ORDER BY
                  CASE WHEN psa.alias_text = ? THEN 0 ELSE 1 END,
                  p.generation,
                  p.primary_page_no,
                  p.name
                LIMIT ?
                """,
                (query, search_like, *([generation] if generation is not None else []), query, limit),
            ).fetchall()

            deduped: Dict[str, Dict[str, Any]] = {}
            priority = {
                "primary_exact": 0,
                "alias_exact": 1,
                "primary_fuzzy": 2,
                "alias_fuzzy": 3,
            }
            for row in [*primary_rows, *alias_rows]:
                item = dict(row)
                current = deduped.get(item["id"])
                if not current or priority[item["match_type"]] < priority[current["match_type"]]:
                    deduped[item["id"]] = item
            rows = sorted(
                deduped.values(),
                key=lambda item: (
                    priority[item["match_type"]],
                    item.get("generation") or 9999,
                    item.get("name") or "",
                ),
            )
            return rows[:limit]
        finally:
            conn.close()

    def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        canonical_person_id = self.resolve_person_id(person_id)
        if not canonical_person_id:
            return None
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                  p.id,
                  p.source_person_id,
                  p.name,
                  p.generation,
                  p.group_id,
                  p.primary_page_no,
                  p.glyph_asset_path,
                  p.glyph_asset_oss_key,
                  p.review_status,
                  p.remark,
                  (
                    SELECT fp.name
                    FROM relationships AS r
                    JOIN persons AS fp
                      ON fp.id = r.parent_person_id
                    WHERE r.child_person_id = p.id
                    ORDER BY r.id
                    LIMIT 1
                  ) AS father_name,
                  EXISTS (
                    SELECT 1 FROM person_biographies AS pb WHERE pb.person_id = p.id
                  ) AS has_biography,
                  EXISTS (
                    SELECT 1 FROM lineage_attachments AS la
                    WHERE la.historical_person_ref = p.id
                      AND la.status = 'active'
                  ) AS has_modern_extension
                FROM persons AS p
                WHERE p.id = ?
                """,
                (canonical_person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_best_biography(self, person_id: str) -> Optional[Dict[str, Any]]:
        canonical_person_id = self.resolve_person_id(person_id)
        if not canonical_person_id:
            return None
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                  pb.person_id,
                  pb.source_title_text,
                  pb.source_text_raw,
                  pb.source_text_linear,
                  pb.source_text_punctuated,
                  pb.source_text_baihua,
                  pb.match_status
                FROM person_biographies AS pb
                WHERE pb.person_id = ?
                ORDER BY
                  CASE pb.match_status
                    WHEN 'reviewed_manual' THEN 0
                    WHEN 'candidate_exact_unique' THEN 1
                    WHEN 'candidate_normalized_unique' THEN 2
                    ELSE 9
                  END,
                  pb.updated_at DESC,
                  pb.id DESC
                LIMIT 1
                """,
                (canonical_person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_ancestor_chain(self, person_id: str, depth: int) -> List[Dict[str, Any]]:
        canonical_person_id = self.resolve_person_id(person_id)
        if not canonical_person_id:
            return []
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE ancestor_chain AS (
                  SELECT
                    1 AS level,
                    p.id,
                    p.source_person_id,
                    p.name,
                    p.generation,
                    p.glyph_asset_path,
                    p.glyph_asset_oss_key,
                    'father_child' AS relation_type
                  FROM relationships AS r
                  JOIN persons AS p
                    ON p.id = r.parent_person_id
                  WHERE r.child_person_id = ?
                  UNION ALL
                  SELECT
                    ancestor_chain.level + 1,
                    p.id,
                    p.source_person_id,
                    p.name,
                    p.generation,
                    p.glyph_asset_path,
                    p.glyph_asset_oss_key,
                    'father_child' AS relation_type
                  FROM ancestor_chain
                  JOIN relationships AS r
                    ON r.child_person_id = ancestor_chain.id
                  JOIN persons AS p
                    ON p.id = r.parent_person_id
                  WHERE ancestor_chain.level < ?
                )
                SELECT * FROM ancestor_chain
                ORDER BY level ASC
                """,
                (canonical_person_id, depth),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_descendant_rows(self, person_id: str, depth: int) -> List[Dict[str, Any]]:
        canonical_person_id = self.resolve_person_id(person_id)
        if not canonical_person_id:
            return []
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE descendant_chain AS (
                  SELECT
                    1 AS level,
                    p.id,
                    p.source_person_id,
                    p.name,
                    p.generation,
                    p.glyph_asset_path,
                    p.glyph_asset_oss_key,
                    r.relation_type
                  FROM relationships AS r
                  JOIN persons AS p
                    ON p.id = r.child_person_id
                  WHERE r.parent_person_id = ?
                  UNION ALL
                  SELECT
                    descendant_chain.level + 1,
                    p.id,
                    p.source_person_id,
                    p.name,
                    p.generation,
                    p.glyph_asset_path,
                    p.glyph_asset_oss_key,
                    r.relation_type
                  FROM descendant_chain
                  JOIN relationships AS r
                    ON r.parent_person_id = descendant_chain.id
                  JOIN persons AS p
                    ON p.id = r.child_person_id
                  WHERE descendant_chain.level < ?
                )
                SELECT * FROM descendant_chain
                ORDER BY level ASC, generation ASC, name ASC
                """,
                (canonical_person_id, depth),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
