from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .persons import PersonSource


class NewPersonPayload(BaseModel):
    display_name: str = Field(..., min_length=1)
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    death_date: Optional[str] = None
    surname: Optional[str] = None
    living_status: Optional[str] = None
    education: Optional[str] = None
    occupation: Optional[str] = None
    bio: Optional[str] = None


class RelationPayload(BaseModel):
    relation_type: Literal["father_son", "father_daughter", "mother_son", "mother_daughter", "spouse"]


class SubmissionCreateRequest(BaseModel):
    target_person_ref: str = Field(..., min_length=1)
    target_person_source: PersonSource
    submitter_name: str = Field(..., min_length=1)
    submitter_contact: Optional[str] = None
    new_person: NewPersonPayload
    relation: RelationPayload
    notes: Optional[str] = None


class SubmissionCreateResponse(BaseModel):
    submission_id: int
    status: Literal["pending"]


class SubmissionItem(BaseModel):
    id: int
    target_person_ref: str
    target_person_source: PersonSource
    submission_type: str
    submitter_name: str
    submitter_contact: Optional[str] = None
    payload_json: str
    status: str
    review_note: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None


class SubmissionListResponse(BaseModel):
    items: List[SubmissionItem]
    total: int


class ReviewRequest(BaseModel):
    review_note: Optional[str] = None


class ReviewResponse(BaseModel):
    submission_id: int
    status: Literal["approved", "rejected"]
