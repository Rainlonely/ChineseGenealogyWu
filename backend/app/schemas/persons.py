from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


PersonSource = Literal["historical", "modern"]


class SearchPersonItem(BaseModel):
    person_ref: str
    person_source: PersonSource
    name: str
    father_name: Optional[str] = None
    generation: Optional[int] = None
    generation_label: str
    has_biography: bool
    has_modern_extension: bool
    glyph_image_url: Optional[str] = None
    summary_route: str
    match_reason: str
    matched_name: str
    match_type: Literal["primary_exact", "primary_fuzzy", "alias_exact", "alias_fuzzy"]


class SearchPersonsResponse(BaseModel):
    items: List[SearchPersonItem]
    total: int


class ActionHints(BaseModel):
    can_view_biography: bool
    can_view_branch: bool
    can_submit_update: bool


class PersonDetail(BaseModel):
    person_ref: str
    person_source: PersonSource
    name: str
    father_name: Optional[str] = None
    generation_label: str
    source_label: str
    has_biography: bool
    has_modern_extension: bool
    glyph_image_url: Optional[str] = None
    modern_extension_note: Optional[str] = None
    biography_summary: Optional[str] = None
    actions: ActionHints


class PersonDetailResponse(BaseModel):
    item: PersonDetail


class BiographyResponse(BaseModel):
    available: bool
    source_type: Literal["historical_biography", "modern_bio", "none"]
    title: Optional[str] = None
    text_raw: Optional[str] = None
    text_linear: Optional[str] = None
    text_punctuated: Optional[str] = None
    text_baihua: Optional[str] = None


class RouteItem(BaseModel):
    generation: Optional[int] = None
    name: str
    person_ref: str
    person_source: PersonSource
    glyph_image_url: Optional[str] = None
    note: str


class RouteResponse(BaseModel):
    items: List[RouteItem]
    has_modern_extension: bool = False
    modern_extension_note: Optional[str] = None


class BranchNode(BaseModel):
    person_ref: str
    person_source: PersonSource
    name: str
    relation_to_focus: str
    node_type: Literal["focus", "ancestor", "descendant", "spouse"]
    relation_type: str
    glyph_image_url: Optional[str] = None


class BranchColumn(BaseModel):
    label: str
    generation: Optional[int] = None
    nodes: List[BranchNode]


class BranchFocus(BaseModel):
    person_ref: str
    person_source: PersonSource
    name: str
    generation_label: str
    glyph_image_url: Optional[str] = None
    has_modern_extension: bool = False
    modern_extension_note: Optional[str] = None


class BranchResponse(BaseModel):
    focus: BranchFocus
    columns: List[BranchColumn]
