from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.repositories.modern import ModernRepository


class SubmissionService:
    def __init__(self, db_path: Path):
        self.repo = ModernRepository(db_path)

    def create_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        submission_id = self.repo.create_submission(payload)
        return {"submission_id": submission_id, "status": "pending"}

    def list_submissions(self) -> Dict[str, Any]:
        items = self.repo.list_submissions()
        return {"items": items, "total": len(items)}

    def approve_submission(self, submission_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        return self.repo.approve_submission(submission_id, review_note)

    def reject_submission(self, submission_id: int, review_note: Optional[str]) -> Dict[str, Any]:
        submission = self.repo.get_submission(submission_id)
        if not submission:
            raise KeyError(f"Submission {submission_id} not found")
        if submission["status"] == "approved":
            raise ValueError("Approved submission cannot be rejected")
        if submission["status"] == "rejected":
            return {"submission_id": submission_id, "status": "rejected"}
        return self.repo.reject_submission(submission_id, review_note)
