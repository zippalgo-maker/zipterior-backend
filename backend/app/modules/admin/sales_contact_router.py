from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin import sales_contact_repository as repo
from app.modules.admin.sales_contact_schemas import (
    SalesContactCreateRequest,
    SalesContactItem,
    SalesContactListResponse,
)
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/api/v1/admin", tags=["admin-sales-contacts"])


def _require_company(session: Session, company_id: int) -> None:
    if not repo.company_exists(session, company_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="업체를 찾을 수 없습니다.",
        )


@router.get(
    "/companies/{company_id}/sales-contacts",
    response_model=SalesContactListResponse,
)
def get_company_sales_contacts(
    company_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    _require_company(session, company_id)
    return {"items": repo.list_sales_contacts(session, company_id)}


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
    try:
        contact = repo.create_sales_contact(
            session,
            company_id=company_id,
            admin_user_id=current_admin["id"],
            content=payload.content,
            contacted_at=payload.contacted_at,
        )
        AuditService.record(
            session=session,
            admin_user_id=current_admin["id"],
            action_type="company.sales_contact_added",
            target_type="company",
            target_id=company_id,
            after_data={"content": payload.content[:200]},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return contact
