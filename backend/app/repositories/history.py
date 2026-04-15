from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.connection import connect


class HistoryRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def search_persons(self, query: str, limit: int) -> List[Dict[str, Any]]:
        search_like = f"%{query}%"
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT
                  p.id,
                  p.name,
                  p.generation,
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
                WHERE p.name LIKE ? OR COALESCE(p.canonical_name, '') LIKE ?
                ORDER BY
                  CASE WHEN p.name = ? THEN 0 ELSE 1 END,
                  p.generation,
                  p.primary_page_no,
                  p.name
                LIMIT ?
                """,
                (search_like, search_like, query, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                  p.id,
                  p.name,
                  p.generation,
                  p.group_id,
                  p.primary_page_no,
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
                (person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_best_biography(self, person_id: str) -> Optional[Dict[str, Any]]:
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
                (person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_ancestor_chain(self, person_id: str, depth: int) -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE ancestor_chain AS (
                  SELECT
                    1 AS level,
                    p.id,
                    p.name,
                    p.generation,
                    'father_child' AS relation_type
                  FROM relationships AS r
                  JOIN persons AS p
                    ON p.id = r.parent_person_id
                  WHERE r.child_person_id = ?
                  UNION ALL
                  SELECT
                    ancestor_chain.level + 1,
                    p.id,
                    p.name,
                    p.generation,
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
                (person_id, depth),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_descendant_rows(self, person_id: str, depth: int) -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE descendant_chain AS (
                  SELECT
                    1 AS level,
                    p.id,
                    p.name,
                    p.generation,
                    r.relation_type
                  FROM relationships AS r
                  JOIN persons AS p
                    ON p.id = r.child_person_id
                  WHERE r.parent_person_id = ?
                  UNION ALL
                  SELECT
                    descendant_chain.level + 1,
                    p.id,
                    p.name,
                    p.generation,
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
                (person_id, depth),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
