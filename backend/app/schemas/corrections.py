from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .persons import PersonSource


class CorrectionCreateRequest(BaseModel):
    target_person_ref: str = Field(..., min_length=1)
    target_person_source: PersonSource
    submitter_name: str = Field(..., min_length=1)
    submitter_contact: Optional[str] = None
    field_name: Literal["name"]
    current_value: Optional[str] = None
    proposed_value: str = Field(..., min_length=1)
    reason: Optional[str] = None
    evidence_note: Optional[str] = None


class CorrectionCreateResponse(BaseModel):
    correction_id: int
    status: Literal["pending"]


class CorrectionItem(BaseModel):
    id: int
    target_person_ref: str
    target_person_source: PersonSource
    field_name: Literal["name"]
    current_value: Optional[str] = None
    proposed_value: str
    submitter_name: str
    submitter_contact: Optional[str] = None
    reason: Optional[str] = None
    evidence_note: Optional[str] = None
    status: str
    resolution_type: Optional[str] = None
    review_note: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None


class CorrectionListResponse(BaseModel):
    items: List[CorrectionItem]
    total: int


class CorrectionApproveRequest(BaseModel):
    resolution_type: Literal["apply_as_primary", "apply_as_alias"]
    review_note: Optional[str] = None


class CorrectionRejectRequest(BaseModel):
    review_note: Optional[str] = None


class CorrectionReviewResponse(BaseModel):
    correction_id: int
    status: Literal["approved", "rejected"]
