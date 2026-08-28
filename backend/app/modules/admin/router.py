from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin.schemas import (
    CompanyActionRequest,
    CompanyActionResponse,
    CompanyBulkStatusRequest,
    CompanyBulkStatusResponse,
    UserActionRequest,
    UserActionResponse,
    UserSuspendRequest,
    UserSuspendResponse,
)
from app.modules.admin.service import (
    AdminCompanyService,
    AdminUserService,
    CompanyNotFoundError,
    InvalidCompanyStatusError,
    InvalidUserStatusError,
    UserNotFoundError,
)


router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
)


def handle_company_error(exc: ValueError) -> None:
    if isinstance(exc, CompanyNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    ) from exc


def handle_user_error(exc: ValueError) -> None:
    if isinstance(exc, UserNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/approve",
    response_model=CompanyActionResponse,
)
def approve_company(
    company_id: int,
    payload: CompanyActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCompanyService.approve(
            session=session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        CompanyNotFoundError,
        InvalidCompanyStatusError,
    ) as exc:
        handle_company_error(exc)


@router.post(
    "/companies/{company_id}/reject",
    response_model=CompanyActionResponse,
)
def reject_company(
    company_id: int,
    payload: CompanyActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCompanyService.reject(
            session=session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        CompanyNotFoundError,
        InvalidCompanyStatusError,
    ) as exc:
        handle_company_error(exc)


@router.post(
    "/companies/{company_id}/suspend",
    response_model=CompanyActionResponse,
)
def suspend_company(
    company_id: int,
    payload: CompanyActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCompanyService.suspend(
            session=session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
            suspend_days=payload.suspend_days,
        )
    except (
        CompanyNotFoundError,
        InvalidCompanyStatusError,
    ) as exc:
        handle_company_error(exc)


@router.post(
    "/companies/{company_id}/unsuspend",
    response_model=CompanyActionResponse,
)
def unsuspend_company(
    company_id: int,
    payload: UserActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCompanyService.unsuspend(
            session=session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        CompanyNotFoundError,
        InvalidCompanyStatusError,
    ) as exc:
        handle_company_error(exc)


@router.post(
    "/companies/bulk-status",
    response_model=CompanyBulkStatusResponse,
)
def bulk_status_companies(
    payload: CompanyBulkStatusRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    """2026-08-25: 업체관리 화면 체크박스(개별/전체선택)로 고른 항목을
    한 번에 승인/반려/정지한다. 상태 조건이 안 맞는 건은 개별 실패로만
    표시되고 나머지는 계속 처리된다(부분 성공 허용) -- 포트폴리오관리
    bulk-status와 동일한 UX."""
    return AdminCompanyService.bulk_status(
        session=session,
        company_ids=payload.company_ids,
        action=payload.action,
        admin_user_id=current_admin["id"],
        reason=payload.reason,
    )


# 2026-08-26: 일반회원(개별 계정) 이용정지/해제 -- 업체 전체를 정지하는
# 위 companies/{id}/suspend와는 별개(회원 개인 계정만 정지).
@router.post(
    "/users/{user_id}/suspend",
    response_model=UserSuspendResponse,
)
def suspend_user(
    user_id: int,
    payload: UserSuspendRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminUserService.suspend(
            session=session,
            user_id=user_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
            suspend_days=payload.suspend_days,
        )
    except (UserNotFoundError, InvalidUserStatusError) as exc:
        handle_user_error(exc)


@router.post(
    "/users/{user_id}/unsuspend",
    response_model=UserActionResponse,
)
def unsuspend_user(
    user_id: int,
    payload: UserActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminUserService.unsuspend(
            session=session,
            user_id=user_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (UserNotFoundError, InvalidUserStatusError) as exc:
        handle_user_error(exc)
