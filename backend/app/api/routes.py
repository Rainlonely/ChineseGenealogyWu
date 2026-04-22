from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.common import HealthResponse
from app.schemas.corrections import (
    CorrectionApproveRequest,
    CorrectionCreateRequest,
    CorrectionCreateResponse,
    CorrectionListResponse,
    CorrectionRejectRequest,
    CorrectionReviewResponse,
)
from app.schemas.persons import (
    BiographyResponse,
    BranchResponse,
    PersonDetailResponse,
    RouteResponse,
    SearchPersonsResponse,
)
from app.schemas.submissions import (
    ReviewRequest,
    ReviewResponse,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
    SubmissionListResponse,
)


def build_router(person_service, submission_service, correction_service, settings) -> APIRouter:
    router = APIRouter()

    def ensure_writable() -> None:
        if settings.read_only:
            raise HTTPException(status_code=403, detail="API is read-only in this deployment")

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            ok=True,
            api_version=settings.api_version,
            db_path=str(settings.db_path),
            read_only=settings.read_only,
        )

    @router.get("/api/v1/search/persons", response_model=SearchPersonsResponse)
    def search_persons(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50)) -> SearchPersonsResponse:
        return SearchPersonsResponse(**person_service.search_persons(q.strip(), limit))

    @router.get("/api/v1/persons/{person_source}/{person_ref}", response_model=PersonDetailResponse)
    def person_detail(person_source: str, person_ref: str) -> PersonDetailResponse:
        try:
            return PersonDetailResponse(**person_service.get_person_detail(person_source, person_ref))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/persons/{person_source}/{person_ref}/biography", response_model=BiographyResponse)
    def person_biography(person_source: str, person_ref: str) -> BiographyResponse:
        try:
            return BiographyResponse(**person_service.get_biography(person_source, person_ref))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/persons/{person_source}/{person_ref}/route", response_model=RouteResponse)
    def person_route(person_source: str, person_ref: str) -> RouteResponse:
        try:
            return RouteResponse(**person_service.get_route(person_source, person_ref))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/persons/{person_source}/{person_ref}/branch", response_model=BranchResponse)
    def person_branch(
        person_source: str,
        person_ref: str,
        up: int = Query(2, ge=1, le=4),
        down: int = Query(3, ge=1, le=5),
        include_daughters: bool = True,
        include_spouses: bool = True,
    ) -> BranchResponse:
        try:
            payload = person_service.get_branch(
                person_source=person_source,
                person_ref=person_ref,
                up=up,
                down=down,
                include_daughters=include_daughters,
                include_spouses=include_spouses,
            )
            return BranchResponse(**payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/v1/submissions", response_model=SubmissionCreateResponse, status_code=201)
    def create_submission(request: SubmissionCreateRequest) -> SubmissionCreateResponse:
        ensure_writable()
        payload = submission_service.create_submission(request.model_dump())
        return SubmissionCreateResponse(**payload)

    @router.post("/api/v1/corrections", response_model=CorrectionCreateResponse, status_code=201)
    def create_correction(request: CorrectionCreateRequest) -> CorrectionCreateResponse:
        ensure_writable()
        payload = correction_service.create_correction_submission(request.model_dump())
        return CorrectionCreateResponse(**payload)

    @router.get("/api/v1/admin/submissions", response_model=SubmissionListResponse)
    def list_submissions() -> SubmissionListResponse:
        return SubmissionListResponse(**submission_service.list_submissions())

    @router.get("/api/v1/admin/corrections", response_model=CorrectionListResponse)
    def list_corrections() -> CorrectionListResponse:
        return CorrectionListResponse(**correction_service.list_correction_submissions())

    @router.post("/api/v1/admin/submissions/{submission_id}/approve", response_model=ReviewResponse)
    def approve_submission(submission_id: int, request: ReviewRequest) -> ReviewResponse:
        ensure_writable()
        try:
            payload = submission_service.approve_submission(submission_id, request.review_note)
            return ReviewResponse(**payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/v1/admin/submissions/{submission_id}/reject", response_model=ReviewResponse)
    def reject_submission(submission_id: int, request: ReviewRequest) -> ReviewResponse:
        ensure_writable()
        try:
            payload = submission_service.reject_submission(submission_id, request.review_note)
            return ReviewResponse(**payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/v1/admin/corrections/{correction_id}/approve", response_model=CorrectionReviewResponse)
    def approve_correction(correction_id: int, request: CorrectionApproveRequest) -> CorrectionReviewResponse:
        ensure_writable()
        try:
            payload = correction_service.approve_correction_submission(
                correction_id,
                request.resolution_type,
                request.review_note,
            )
            return CorrectionReviewResponse(**payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/v1/admin/corrections/{correction_id}/reject", response_model=CorrectionReviewResponse)
    def reject_correction(correction_id: int, request: CorrectionRejectRequest) -> CorrectionReviewResponse:
        ensure_writable()
        try:
            payload = correction_service.reject_correction_submission(correction_id, request.review_note)
            return CorrectionReviewResponse(**payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
