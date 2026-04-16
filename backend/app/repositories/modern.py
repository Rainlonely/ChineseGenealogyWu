from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.connection import connect


class ModernRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def search_persons(self, query: str, limit: int) -> List[Dict[str, Any]]:
        search_like = f"%{query}%"
        conn = connect(self.db_path)
        try:
            primary_rows = conn.execute(
                """
                SELECT
                  mp.id,
                  mp.display_name,
                  (
                    SELECT parent.display_name
                    FROM modern_relationships AS mr
                    JOIN modern_persons AS parent
                      ON parent.id = mr.from_person_ref
                    WHERE mr.to_person_ref = mp.id
                      AND mr.to_person_source = 'modern'
                      AND mr.from_person_source = 'modern'
                      AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                    ORDER BY mr.id
                    LIMIT 1
                  ) AS father_name,
                  CASE
                    WHEN COALESCE(mp.bio, '') <> '' THEN 1
                    ELSE 0
                  END AS has_biography,
                  EXISTS (
                    SELECT 1
                    FROM modern_relationships AS child
                    WHERE child.from_person_ref = mp.id
                      AND child.from_person_source = 'modern'
                      AND child.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  ) AS has_modern_extension
                  ,
                  CASE
                    WHEN mp.display_name = ? THEN 'primary_exact'
                    ELSE 'primary_fuzzy'
                  END AS match_type,
                  mp.display_name AS matched_name
                FROM modern_persons AS mp
                WHERE mp.status = 'active'
                  AND mp.display_name LIKE ?
                ORDER BY
                  CASE WHEN mp.display_name = ? THEN 0 ELSE 1 END,
                  mp.display_name ASC,
                  mp.id ASC
                LIMIT ?
                """,
                (query, search_like, query, limit),
            ).fetchall()
            alias_rows = conn.execute(
                """
                SELECT
                  mp.id,
                  mp.display_name,
                  (
                    SELECT parent.display_name
                    FROM modern_relationships AS mr
                    JOIN modern_persons AS parent
                      ON parent.id = mr.from_person_ref
                    WHERE mr.to_person_ref = mp.id
                      AND mr.to_person_source = 'modern'
                      AND mr.from_person_source = 'modern'
                      AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                    ORDER BY mr.id
                    LIMIT 1
                  ) AS father_name,
                  CASE
                    WHEN COALESCE(mp.bio, '') <> '' THEN 1
                    ELSE 0
                  END AS has_biography,
                  EXISTS (
                    SELECT 1
                    FROM modern_relationships AS child
                    WHERE child.from_person_ref = mp.id
                      AND child.from_person_source = 'modern'
                      AND child.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  ) AS has_modern_extension,
                  CASE
                    WHEN psa.alias_text = ? THEN 'alias_exact'
                    ELSE 'alias_fuzzy'
                  END AS match_type,
                  psa.alias_text AS matched_name
                FROM person_search_aliases AS psa
                JOIN modern_persons AS mp
                  ON mp.id = psa.person_ref
                WHERE psa.person_source = 'modern'
                  AND psa.status = 'active'
                  AND mp.status = 'active'
                  AND psa.alias_text LIKE ?
                ORDER BY
                  CASE WHEN psa.alias_text = ? THEN 0 ELSE 1 END,
                  mp.display_name ASC,
                  mp.id ASC
                LIMIT ?
                """,
                (query, search_like, query, limit),
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
                    item.get("display_name") or "",
                    item.get("id") or "",
                ),
            )
            return rows[:limit]
        finally:
            conn.close()

    def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT
                  mp.id,
                  mp.display_name,
                  mp.gender,
                  mp.birth_date,
                  mp.death_date,
                  mp.living_status,
                  mp.surname,
                  mp.is_external_surname,
                  mp.education,
                  mp.occupation,
                  mp.bio,
                  (
                    SELECT parent.display_name
                    FROM modern_relationships AS mr
                    JOIN modern_persons AS parent
                      ON parent.id = mr.from_person_ref
                    WHERE mr.to_person_ref = mp.id
                      AND mr.to_person_source = 'modern'
                      AND mr.from_person_source = 'modern'
                      AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                    ORDER BY mr.id
                    LIMIT 1
                  ) AS father_name,
                  EXISTS (
                    SELECT 1 FROM modern_relationships AS child
                    WHERE child.from_person_ref = mp.id
                      AND child.from_person_source = 'modern'
                      AND child.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  ) AS has_modern_extension
                FROM modern_persons AS mp
                WHERE mp.id = ?
                  AND mp.status = 'active'
                """,
                (person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_attachment_for_modern(self, person_id: str) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                WITH RECURSIVE modern_chain AS (
                  SELECT 0 AS level, ? AS person_id
                  UNION ALL
                  SELECT
                    modern_chain.level + 1,
                    mr.from_person_ref
                  FROM modern_chain
                  JOIN modern_relationships AS mr
                    ON mr.to_person_ref = modern_chain.person_id
                   AND mr.to_person_source = 'modern'
                   AND mr.from_person_source = 'modern'
                   AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  WHERE modern_chain.level < 8
                )
                SELECT la.historical_person_ref, la.modern_person_ref, modern_chain.person_id
                FROM modern_chain
                JOIN lineage_attachments AS la
                  ON la.modern_person_ref = modern_chain.person_id
                 AND la.status = 'active'
                ORDER BY modern_chain.level ASC
                LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_attached_roots(self, historical_person_ref: str) -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT mp.id, mp.display_name, mp.bio
                FROM lineage_attachments AS la
                JOIN modern_persons AS mp
                  ON mp.id = la.modern_person_ref
                WHERE la.historical_person_ref = ?
                  AND la.status = 'active'
                  AND mp.status = 'active'
                ORDER BY mp.id
                """,
                (historical_person_ref,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_descendants_from_roots(self, root_ids: List[str], depth: int) -> List[Dict[str, Any]]:
        if not root_ids:
            return []
        placeholders = ",".join("?" for _ in root_ids)
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                f"""
                WITH RECURSIVE descendant_chain AS (
                  SELECT
                    1 AS level,
                    mr.to_person_ref AS person_id,
                    mp.display_name,
                    mr.relation_type
                  FROM modern_relationships AS mr
                  JOIN modern_persons AS mp
                    ON mp.id = mr.to_person_ref
                  WHERE mr.from_person_source = 'modern'
                    AND mr.to_person_source = 'modern'
                    AND mr.from_person_ref IN ({placeholders})
                    AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  UNION ALL
                  SELECT
                    descendant_chain.level + 1,
                    mr.to_person_ref AS person_id,
                    mp.display_name,
                    mr.relation_type
                  FROM descendant_chain
                  JOIN modern_relationships AS mr
                    ON mr.from_person_ref = descendant_chain.person_id
                   AND mr.from_person_source = 'modern'
                   AND mr.to_person_source = 'modern'
                   AND mr.relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter')
                  JOIN modern_persons AS mp
                    ON mp.id = mr.to_person_ref
                  WHERE descendant_chain.level < ?
                )
                SELECT * FROM descendant_chain
                ORDER BY level ASC, display_name ASC
                """,
                (*root_ids, depth),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_spouses(self, person_refs: List[str], person_source: str) -> List[Dict[str, Any]]:
        if not person_refs:
            return []
        anchor_ref = person_refs[0]
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT
                  mr.id,
                  mr.from_person_ref,
                  mr.to_person_ref,
                  mr.from_person_source,
                  mr.to_person_source,
                  mr.relation_type,
                  CASE
                    WHEN mr.from_person_ref = ? AND mr.to_person_source = 'modern' THEN mp_to.display_name
                    WHEN mr.to_person_ref = ? AND mr.from_person_source = 'modern' THEN mp_from.display_name
                    ELSE NULL
                  END AS spouse_name,
                  CASE
                    WHEN mr.from_person_ref = ? THEN mr.from_person_ref
                    ELSE mr.to_person_ref
                  END AS anchor_person_ref,
                  CASE
                    WHEN mr.from_person_ref = ? THEN mr.from_person_source
                    ELSE mr.to_person_source
                  END AS anchor_person_source,
                  CASE
                    WHEN mr.from_person_ref = ? THEN mr.to_person_ref
                    ELSE mr.from_person_ref
                  END AS spouse_person_ref,
                  CASE
                    WHEN mr.from_person_ref = ? THEN mr.to_person_source
                    ELSE mr.from_person_source
                  END AS spouse_person_source
                FROM modern_relationships AS mr
                LEFT JOIN modern_persons AS mp_to
                  ON mp_to.id = mr.to_person_ref
                LEFT JOIN modern_persons AS mp_from
                  ON mp_from.id = mr.from_person_ref
                WHERE mr.relation_type = 'spouse'
                  AND (
                    (mr.from_person_source = ? AND mr.from_person_ref = ?)
                    OR
                    (mr.to_person_source = ? AND mr.to_person_ref = ?)
                  )
                ORDER BY mr.id
                """,
                (
                    anchor_ref,
                    anchor_ref,
                    anchor_ref,
                    anchor_ref,
                    anchor_ref,
                    anchor_ref,
                    person_source,
                    anchor_ref,
                    person_source,
                    anchor_ref,
                ),
            ).fetchall()
            return [dict(row) for row in rows if row["spouse_name"]]
        finally:
            conn.close()

    def create_submission(self, payload: Dict[str, Any]) -> int:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO change_submissions (
                  target_person_ref,
                  target_person_source,
                  submission_type,
                  submitter_name,
                  submitter_contact,
                  payload_json,
                  status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    payload["target_person_ref"],
                    payload["target_person_source"],
                    "add_person_with_relation",
                    payload["submitter_name"],
                    payload.get("submitter_contact"),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def create_correction_submission(self, payload: Dict[str, Any]) -> int:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO correction_submissions (
                  target_person_ref,
                  target_person_source,
                  field_name,
                  current_value,
                  proposed_value,
                  submitter_name,
                  submitter_contact,
                  reason,
                  evidence_note,
                  status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    payload["target_person_ref"],
                    payload["target_person_source"],
                    payload["field_name"],
                    payload.get("current_value"),
                    payload["proposed_value"],
                    payload["submitter_name"],
                    payload.get("submitter_contact"),
                    payload.get("reason"),
                    payload.get("evidence_note"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def list_correction_submissions(self) -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM correction_submissions
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_correction_submission(self, correction_id: int) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM correction_submissions WHERE id = ?",
                (correction_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def add_person_alias(
        self,
        person_ref: str,
        person_source: str,
        alias_text: str,
        alias_type: str,
        source_submission_id: Optional[int] = None,
    ) -> None:
        if not alias_text:
            return
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO person_search_aliases (
                  person_ref,
                  person_source,
                  alias_text,
                  alias_type,
                  source_submission_id,
                  status
                ) VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (person_ref, person_source, alias_text, alias_type, source_submission_id),
            )
            conn.commit()
        finally:
            conn.close()

    def reject_correction_submission(self, correction_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE correction_submissions
                SET status = 'rejected',
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'pending'
                """,
                (review_note, correction_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"correction_id": correction_id, "status": "rejected"}

    def approve_correction_submission(
        self,
        correction_id: int,
        resolution_type: str,
        review_note: Optional[str],
    ) -> Dict[str, Any]:
        correction = self.get_correction_submission(correction_id)
        if not correction:
            raise KeyError(f"Correction submission {correction_id} not found")
        if correction["status"] == "approved":
            return {"correction_id": correction_id, "status": "approved"}
        if correction["status"] == "rejected":
            raise ValueError("Rejected correction cannot be approved")

        person_ref = correction["target_person_ref"]
        person_source = correction["target_person_source"]
        current_value = correction.get("current_value")
        proposed_value = correction["proposed_value"]

        conn = connect(self.db_path)
        try:
            if resolution_type == "apply_as_primary":
                if person_source == "historical":
                    conn.execute(
                        """
                        UPDATE persons
                        SET name = ?, canonical_name = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (proposed_value, proposed_value, person_ref),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE modern_persons
                        SET display_name = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (proposed_value, person_ref),
                    )
                if current_value and current_value != proposed_value:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO person_search_aliases (
                          person_ref,
                          person_source,
                          alias_text,
                          alias_type,
                          source_submission_id,
                          status
                        ) VALUES (?, ?, ?, 'correction_accepted', ?, 'active')
                        """,
                        (person_ref, person_source, current_value, correction_id),
                    )
            if proposed_value:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO person_search_aliases (
                      person_ref,
                      person_source,
                      alias_text,
                      alias_type,
                      source_submission_id,
                      status
                    ) VALUES (?, ?, ?, 'correction_accepted', ?, 'active')
                    """,
                    (person_ref, person_source, proposed_value, correction_id),
                )
            conn.execute(
                """
                UPDATE correction_submissions
                SET status = 'approved',
                    resolution_type = ?,
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (resolution_type, review_note, correction_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"correction_id": correction_id, "status": "approved"}

    def list_submissions(self) -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM change_submissions
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_submission(self, submission_id: int) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM change_submissions WHERE id = ?",
                (submission_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def reject_submission(self, submission_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE change_submissions
                SET status = 'rejected',
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'pending'
                """,
                (review_note, submission_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"submission_id": submission_id, "status": "rejected"}

    def approve_submission(self, submission_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        submission = self.get_submission(submission_id)
        if not submission:
            raise KeyError(f"Submission {submission_id} not found")
        if submission["status"] == "approved":
            return {"submission_id": submission_id, "status": "approved"}
        if submission["status"] == "rejected":
            raise ValueError("Rejected submission cannot be approved")

        payload = json.loads(submission["payload_json"])
        new_person_id = f"modern_{uuid.uuid4().hex[:12]}"
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO modern_persons (
                  id,
                  display_name,
                  gender,
                  birth_date,
                  death_date,
                  living_status,
                  surname,
                  education,
                  occupation,
                  bio,
                  created_from_submission_id,
                  status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    new_person_id,
                    payload["new_person"]["display_name"],
                    payload["new_person"].get("gender"),
                    payload["new_person"].get("birth_date"),
                    payload["new_person"].get("death_date"),
                    payload["new_person"].get("living_status"),
                    payload["new_person"].get("surname"),
                    payload["new_person"].get("education"),
                    payload["new_person"].get("occupation"),
                    payload["new_person"].get("bio"),
                    submission_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO modern_relationships (
                  from_person_ref,
                  to_person_ref,
                  from_person_source,
                  to_person_source,
                  relation_type,
                  status,
                  created_from_submission_id
                ) VALUES (?, ?, ?, 'modern', ?, 'active', ?)
                """,
                (
                    payload["target_person_ref"],
                    new_person_id,
                    payload["target_person_source"],
                    payload["relation"]["relation_type"],
                    submission_id,
                ),
            )
            if payload["target_person_source"] == "historical":
                conn.execute(
                    """
                    INSERT OR IGNORE INTO lineage_attachments (
                      historical_person_ref,
                      modern_person_ref,
                      created_from_submission_id,
                      status
                    ) VALUES (?, ?, ?, 'active')
                    """,
                    (payload["target_person_ref"], new_person_id, submission_id),
                )
            conn.execute(
                """
                UPDATE change_submissions
                SET status = 'approved',
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (review_note, submission_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"submission_id": submission_id, "status": "approved"}
