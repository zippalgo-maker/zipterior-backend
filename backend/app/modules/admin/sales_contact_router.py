from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.common.rich_text import sanitize_rich_text
from app.core.database import get_db
from app.modules.admin import sales_contact_repository as repo
from app.modules.admin.sales_contact_schemas import (
    SalesContactCodeCreateRequest,
    SalesContactCodeItem,
    SalesContactCodeListResponse,
    SalesContactCreateRequest,
    SalesContactDetailResponse,
    SalesContactItem,
    SalesContactListResponse,
    SalesContactUpdateRequest,
)
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/api/v1/admin", tags=["admin-sales-contacts"])


def _require_company(session: Session, company_id: int) -> None:
    if not repo.company_exists(session, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="업체를 찾을 수 없습니다.",
        )


def _require_contact(session: Session, company_id: int, contact_id: int) -> dict:
    contact = repo.get_sales_contact(session, contact_id)
    if contact is None or contact["company_id"] != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="통화기록을 찾을 수 없습니다.",
        )
    return contact


# --- 코드(상태/TM내용) 관리 --------------------------------------------


@router.get("/sales-contact-codes", response_model=SalesContactCodeListResponse)
def get_sales_contact_codes(
    current_admin: CurrentAdmin,
    code_type: str | None = Query(default=None, pattern="^(status|reason)$"),
    session: Session = Depends(get_db),
) -> dict:
    return {"items": repo.list_codes(session, code_type)}


@router.post(
    "/sales-contact-codes",
    response_model=SalesContactCodeItem,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_contact_code(
    payload: SalesContactCodeCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        code = repo.create_code(session, code_type=payload.code_type, label=payload.label)
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="sales_contact_code.created",
            target_type="sales_contact_code",
            target_id=code["id"],
            after_data={"code_type": payload.code_type, "label": payload.label},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return code


# --- 통화기록 -------------------------------------------------------------


@router.get(
    "/companies/{company_id}/sales-contacts",
    response_model=SalesContactListResponse,
)
def get_company_sales_contacts(
    company_id: int,
    current_admin: CurrentAdmin,
    admin_user_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    weekday: int | None = Query(default=None, ge=0, le=6, description="0=일요일 ... 6=토요일"),
    q: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    _require_company(session, company_id)
    items, total = repo.list_sales_contacts(
        session,
        company_id,
        admin_user_id=admin_user_id,
        date_from=date_from,
        date_to=date_to,
        weekday=weekday,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total}


@router.get(
    "/companies/{company_id}/sales-contacts/{contact_id}",
    response_model=SalesContactDetailResponse,
)
def get_company_sales_contact_detail(
    company_id: int,
    contact_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    _require_company(session, company_id)
    contact = _require_contact(session, company_id, contact_id)
    return {"contact": contact, "edits": repo.list_edits(session, contact_id)}


@router.post(
    "/companies/{company_id}/sales-contacts",
    response_model=SalesContactItem,
    status_code=status.HTTP_201_CREATED,
)
def create_company_sales_contact(
    company_id: int,
    payload: SalesContactCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    _require_company(session, company_id)
    content = sanitize_rich_text(payload.content)
    try:
        contact_id = repo.create_sales_contact(
            session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            content=content,
            contacted_at=payload.contacted_at,
            status_code_id=payload.status_code_id,
            reason_code_id=payload.reason_code_id,
        )
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="company.sales_contact_added",
            target_type="company",
            target_id=company_id,
            after_data={"content": content[:200]},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return repo.get_sales_contact(session, contact_id)


@router.patch(
    "/companies/{company_id}/sales-contacts/{contact_id}",
    response_model=SalesContactItem,
)
def update_company_sales_contact(
    company_id: int,
    contact_id: int,
    payload: SalesContactUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    _require_company(session, company_id)
    _require_contact(session, company_id, contact_id)
    content = sanitize_rich_text(payload.content)
    try:
        repo.update_sales_contact(
            session,
            contact_id=contact_id,
            admin_user_id=current_admin["id"],
            content=content,
            status_code_id=payload.status_code_id,
            reason_code_id=payload.reason_code_id,
            contacted_at=payload.contacted_at,
            reason=payload.reason,
        )
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="company.sales_contact_edited",
            target_type="company_sales_contact",
            target_id=contact_id,
            after_data={"content": content[:200]},
            reason=payload.reason,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return repo.get_sales_contact(session, contact_id)
