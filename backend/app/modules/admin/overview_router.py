from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin import overview_repository as repo
from app.modules.admin.overview_schemas import (
    AdminDashboardResponse, AdminUserListResponse, AdminCompanyListResponse,
    AdminActionLogListResponse, AdminUserDetailResponse, AdminReasonRequest,
    AdminUnlinkOAuthResponse, AdminRevokeSessionsResponse,
    OrphanedOAuthAccountListResponse, AdminDeleteResponse,
    AdminCompanyDetailResponse, AdminCompanyCreateRequest,
)
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/api/v1/admin", tags=["admin-overview"])

@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_admin_dashboard(current_admin: CurrentAdmin, session: Session = Depends(get_db)) -> dict:
    return repo.dashboard(session)

@router.get("/users", response_model=AdminUserListResponse)
def get_admin_users(current_admin: CurrentAdmin, q: str | None = Query(default=None, max_length=100), role: str | None = Query(default=None), user_status: str | None = Query(default=None, alias="status"), limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    items,total=repo.list_users(session,q=q,role=role,user_status=user_status,limit=limit,offset=offset)
    return {"items":items,"total":total,"limit":limit,"offset":offset}

@router.get("/companies", response_model=AdminCompanyListResponse)
def get_admin_companies(current_admin: CurrentAdmin, q: str | None = Query(default=None, max_length=100), company_status: str | None = Query(default=None, alias="status"), sido: str | None = Query(default=None, max_length=20), plan_key: str | None = Query(default=None, max_length=30), limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    items,total=repo.list_companies(session,q=q,company_status=company_status,sido=sido,plan_key=plan_key,limit=limit,offset=offset)
    return {"items":items,"total":total,"limit":limit,"offset":offset}


# 2026-08-28: 업체관리 "등록" 버튼 -- 관리자가 로그인 계정 없이 업체
# 정보만 직접 등록(bulk_import와 동일한 owner_user_id=NULL 방식). 사업자
# 등록번호가 이미 있는 업체면 막는다(자체가입 CompanyBusinessNumberExistsError
# 와 동일한 취지).
@router.post("/companies", response_model=AdminCompanyDetailResponse, status_code=status.HTTP_201_CREATED)
def create_admin_company(
    payload: AdminCompanyCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    if payload.business_number and repo.find_company_by_business_number(session, payload.business_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 사업자등록번호입니다.",
        )
    try:
        company_id = repo.create_company_admin(
            session,
            name=payload.name,
            business_number=payload.business_number,
            representative_name=payload.representative_name,
            phone=payload.phone,
            email=payload.email,
            postal_code=payload.postal_code,
            address=payload.address,
            address_detail=payload.address_detail,
            sido=payload.sido,
            sigungu=payload.sigungu,
            eupmyeondong=payload.eupmyeondong,
            intro=payload.intro,
            website_url=payload.website_url,
            approved_by=current_admin["id"],
        )
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="company.created_by_admin",
            target_type="company",
            target_id=company_id,
            after_data={"name": payload.name, "business_number": payload.business_number},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return repo.get_company_detail(session, company_id)


# 2026-08-25: 업체관리 "상세" 버튼용(회원 상세 get_admin_user_detail과 동일 패턴).
@router.get("/companies/{company_id}", response_model=AdminCompanyDetailResponse)
def get_admin_company_detail(
    company_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    company = repo.get_company_detail(session, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="업체를 찾을 수 없습니다.")
    return company

@router.get("/action-logs", response_model=AdminActionLogListResponse)
def get_admin_action_logs(current_admin: CurrentAdmin, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db)) -> dict:
    items,total=repo.list_action_logs(session,limit=limit,offset=offset)
    return {"items":items,"total":total,"limit":limit,"offset":offset}


def _require_user(session: Session, user_id: int) -> dict:
    user = repo.get_user_detail(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="회원을 찾을 수 없습니다.")
    return user


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def get_admin_user_detail(
    user_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    user = _require_user(session, user_id)
    oauth_accounts = repo.list_oauth_accounts_for_user(session, user_id)
    recent_login_attempts = repo.list_login_attempts(
        session, user_id=user_id, email=user["email"], limit=15,
    )
    return {
        **user,
        "oauth_accounts": oauth_accounts,
        "recent_login_attempts": recent_login_attempts,
    }


@router.delete(
    "/users/{user_id}/oauth-accounts/{provider}",
    response_model=AdminUnlinkOAuthResponse,
)
def unlink_admin_user_oauth_account(
    user_id: int,
    provider: str,
    payload: AdminReasonRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    user = _require_user(session, user_id)
    account = repo.find_oauth_account_by_user_and_provider(
        session, user_id=user_id, provider=provider,
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연동된 SNS 계정을 찾을 수 없습니다.",
        )

    # 안전장치: 비밀번호도 없고(SNS 전용 가입) 이게 마지막 연동이면
    # 해제 즉시 로그인 수단이 완전히 없어진다 -- 차단.
    other_links = repo.count_oauth_accounts_for_user(session, user_id) - 1
    if not user["has_password"] and other_links == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "이 회원은 비밀번호가 없고 다른 SNS 연동도 없습니다. "
                "지금 해제하면 로그인할 방법이 없어집니다."
            ),
        )

    try:
        repo.delete_oauth_account(session, account["id"])
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="user.oauth_unlinked",
            target_type="user",
            target_id=user_id,
            before_data={
                "provider": account["provider"],
                "provider_user_id": account["provider_user_id"],
            },
            after_data=None,
            reason=payload.reason,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "user_id": user_id,
        "provider": provider,
        "message": "SNS 연동이 해제되었습니다.",
    }


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=AdminRevokeSessionsResponse,
)
def revoke_admin_user_sessions(
    user_id: int,
    payload: AdminReasonRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    _require_user(session, user_id)
    try:
        revoked = repo.revoke_user_sessions(session, user_id, "admin_forced_logout")
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="user.sessions_revoked",
            target_type="user",
            target_id=user_id,
            before_data=None,
            after_data={"revoked_count": revoked},
            reason=payload.reason,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "user_id": user_id,
        "revoked_count": revoked,
        "message": "모든 로그인 세션을 종료했습니다.",
    }


@router.get("/oauth-accounts/orphaned", response_model=OrphanedOAuthAccountListResponse)
def get_orphaned_oauth_accounts(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return {"items": repo.list_orphaned_oauth_accounts(session)}


@router.delete("/oauth-accounts/{oauth_account_id}", response_model=AdminDeleteResponse)
def delete_orphaned_oauth_account(
    oauth_account_id: int,
    payload: AdminReasonRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        repo.delete_oauth_account(session, oauth_account_id)
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="oauth_account.orphan_deleted",
            target_type="user_oauth_account",
            target_id=oauth_account_id,
            before_data=None,
            after_data=None,
            reason=payload.reason,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {"id": oauth_account_id, "message": "삭제되었습니다."}
