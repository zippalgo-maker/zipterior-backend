from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin, CurrentUser
from app.core.database import get_db
from app.modules.estimates.schemas import (
    AdminEstimateAssignRequest,
    AdminEstimateAutoAssignRequest,
    AdminEstimateAutoAssignResponse,
    AdminEstimateAssignResponse,
    AdminEstimateStatusRequest,
    AdminEstimateStatusResponse,
    AssignmentStatus,
    CompanyEstimateActionResponse,
    CompanyEstimateListResponse,
    CompanyEstimateResponse,
    CompanyInsightsResponse,
    EstimateCancelResponse,
    EstimateCreateRequest,
    EstimateImageDeleteResponse,
    EstimateImageUploadResponse,
    EstimateListResponse,
    EstimateMilestoneListResponse,
    EstimateMilestoneUpdateRequest,
    EstimateResponse,
    EstimateStatus,
)
from app.modules.estimates.service import (
    EstimateAccessDeniedError,
    EstimateNotFoundError,
    EstimateService,
    EstimateStateConflictError,
    EstimateValidationError,
)


router = APIRouter(tags=["estimates"])


def handle_estimate_error(exc: ValueError) -> None:
    if isinstance(exc, EstimateNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, EstimateAccessDeniedError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, EstimateStateConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/api/v1/estimates", response_model=EstimateResponse, status_code=status.HTTP_201_CREATED)
def create_estimate(payload: EstimateCreateRequest, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.create(session, user=current_user, payload=payload)
    except (EstimateAccessDeniedError, EstimateValidationError) as exc:
        handle_estimate_error(exc)


@router.get("/api/v1/estimates", response_model=EstimateListResponse)
def list_my_estimates(current_user: CurrentUser, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.list_mine(session, user=current_user, limit=limit, offset=offset)
    except EstimateAccessDeniedError as exc:
        handle_estimate_error(exc)


@router.get("/api/v1/estimates/{estimate_id}", response_model=EstimateResponse)
def get_my_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.get_mine(session, user=current_user, estimate_id=estimate_id)
    except (EstimateAccessDeniedError, EstimateNotFoundError) as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/estimates/{estimate_id}/cancel", response_model=EstimateCancelResponse)
def cancel_my_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.cancel(session, user=current_user, estimate_id=estimate_id)
    except (EstimateAccessDeniedError, EstimateNotFoundError, EstimateStateConflictError) as exc:
        handle_estimate_error(exc)


@router.get("/api/v1/company/insights", response_model=CompanyInsightsResponse)
def get_company_insights(current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.company_insights(session, user=current_user)
    except EstimateAccessDeniedError as exc:
        handle_estimate_error(exc)


@router.get("/api/v1/company/estimates", response_model=CompanyEstimateListResponse)
def list_company_estimates(current_user: CurrentUser, assignment_status: AssignmentStatus | None = Query(default=None), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.list_company(session, user=current_user, assignment_status=assignment_status, limit=limit, offset=offset)
    except EstimateAccessDeniedError as exc:
        handle_estimate_error(exc)


@router.get("/api/v1/company/estimates/{estimate_id}", response_model=CompanyEstimateResponse)
def get_company_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.get_company(session, user=current_user, estimate_id=estimate_id)
    except (EstimateAccessDeniedError, EstimateNotFoundError) as exc:
        handle_estimate_error(exc)


def _company_action(estimate_id: int, action: str, current_user: dict, session: Session) -> dict:
    try:
        return EstimateService.company_action(session, user=current_user, estimate_id=estimate_id, action=action)
    except (EstimateAccessDeniedError, EstimateNotFoundError, EstimateStateConflictError) as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/company/estimates/{estimate_id}/view", response_model=CompanyEstimateActionResponse)
def view_company_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return _company_action(estimate_id, "view", current_user, session)


@router.post("/api/v1/company/estimates/{estimate_id}/respond", response_model=CompanyEstimateActionResponse)
def respond_company_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return _company_action(estimate_id, "respond", current_user, session)


@router.post("/api/v1/company/estimates/{estimate_id}/decline", response_model=CompanyEstimateActionResponse)
def decline_company_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return _company_action(estimate_id, "decline", current_user, session)


@router.post("/api/v1/company/estimates/{estimate_id}/contract", response_model=CompanyEstimateActionResponse)
def contract_company_estimate(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return _company_action(estimate_id, "contract", current_user, session)


@router.get("/api/v1/admin/estimates", response_model=EstimateListResponse)
def list_admin_estimates(current_admin: CurrentAdmin, estimate_status: EstimateStatus | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    return EstimateService.list_admin(session, estimate_status=estimate_status, limit=limit, offset=offset)


@router.get("/api/v1/admin/estimates/{estimate_id}", response_model=EstimateResponse)
def get_admin_estimate(estimate_id: int, current_admin: CurrentAdmin, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.get_admin(session, estimate_id=estimate_id)
    except EstimateNotFoundError as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/admin/estimates/{estimate_id}/assign", response_model=AdminEstimateAssignResponse)
def assign_admin_estimate(estimate_id: int, payload: AdminEstimateAssignRequest, current_admin: CurrentAdmin, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.assign_admin(session, admin_user_id=current_admin["id"], estimate_id=estimate_id, company_ids=payload.company_ids)
    except (EstimateNotFoundError, EstimateStateConflictError, EstimateValidationError) as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/admin/estimates/{estimate_id}/status", response_model=AdminEstimateStatusResponse)
def set_admin_estimate_status(estimate_id: int, payload: AdminEstimateStatusRequest, current_admin: CurrentAdmin, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.set_admin_status(session, admin_user_id=current_admin["id"], estimate_id=estimate_id, status=payload.status, reason=payload.reason)
    except EstimateNotFoundError as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/estimates/{estimate_id}/images", response_model=EstimateImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_estimate_image(
    estimate_id: int,
    current_user: CurrentUser,
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await EstimateService.upload_image(session, user=current_user, estimate_id=estimate_id, upload=upload)
    except (EstimateAccessDeniedError, EstimateNotFoundError, EstimateStateConflictError, EstimateValidationError) as exc:
        handle_estimate_error(exc)


@router.delete("/api/v1/estimates/{estimate_id}/images/{image_id}", response_model=EstimateImageDeleteResponse)
def delete_estimate_image(
    estimate_id: int,
    image_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return EstimateService.delete_image(session, user=current_user, estimate_id=estimate_id, image_id=image_id)
    except (EstimateAccessDeniedError, EstimateNotFoundError, EstimateStateConflictError) as exc:
        handle_estimate_error(exc)


@router.post("/api/v1/admin/estimates/{estimate_id}/auto-assign", response_model=AdminEstimateAutoAssignResponse)
def auto_assign_admin_estimate(
    estimate_id: int,
    payload: AdminEstimateAutoAssignRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return EstimateService.auto_assign_admin(session, admin_user_id=current_admin["id"], estimate_id=estimate_id, limit=payload.limit)
    except (EstimateNotFoundError, EstimateStateConflictError, EstimateValidationError) as exc:
        handle_estimate_error(exc)


# v1.10.1(2026-08-26): 시공 진행상황(목업 13번 화면) -- 고객/업체/관리자
# 공용 조회, 업데이트는 업체(계약 확정 건)·관리자만.
@router.get("/api/v1/estimates/{estimate_id}/milestones", response_model=EstimateMilestoneListResponse)
def get_estimate_milestones(estimate_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return EstimateService.get_milestones(session, user=current_user, estimate_id=estimate_id)
    except (EstimateAccessDeniedError, EstimateNotFoundError) as exc:
        handle_estimate_error(exc)


@router.patch("/api/v1/estimates/{estimate_id}/milestones/{phase_key}", response_model=EstimateMilestoneListResponse)
def update_estimate_milestone(
    estimate_id: int,
    phase_key: str,
    payload: EstimateMilestoneUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return EstimateService.update_milestone(
            session, user=current_user, estimate_id=estimate_id, phase_key=phase_key,
            status=payload.status, note=payload.note,
        )
    except (EstimateAccessDeniedError, EstimateNotFoundError, EstimateStateConflictError) as exc:
        handle_estimate_error(exc)
