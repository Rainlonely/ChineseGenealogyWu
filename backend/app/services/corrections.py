from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.repositories.modern import ModernRepository


class CorrectionService:
    def __init__(self, db_path: Path):
        self.repo = ModernRepository(db_path)

    def create_correction_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        correction_id = self.repo.create_correction_submission(payload)
        return self.repo.approve_correction_submission(
            correction_id,
            "apply_as_primary",
            "自动应用姓名勘误",
        )

    def list_correction_submissions(self) -> Dict[str, Any]:
        items = self.repo.list_correction_submissions()
        return {"items": items, "total": len(items)}

    def approve_correction_submission(
        self,
        correction_id: int,
        resolution_type: str,
        review_note: Optional[str],
    ) -> Dict[str, Any]:
        return self.repo.approve_correction_submission(correction_id, resolution_type, review_note)

    def reject_correction_submission(self, correction_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        correction = self.repo.get_correction_submission(correction_id)
        if not correction:
            raise KeyError(f"Correction submission {correction_id} not found")
        if correction["status"] == "approved":
            raise ValueError("Approved correction cannot be rejected")
        if correction["status"] == "rejected":
            return {"correction_id": correction_id, "status": "rejected"}
        return self.repo.reject_correction_submission(correction_id, review_note)
