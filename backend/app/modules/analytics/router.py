from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin, CurrentUser, OptionalCurrentUser
from app.core.database import get_db
from app.modules.analytics import repository
from app.modules.analytics.schemas import (
    AnalyticsEventAccepted,
    AnalyticsEventBatch,
    AnalyticsReport,
)
from app.modules.analytics.service import AnalyticsEventService, AnalyticsReportService


router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
company_router = APIRouter(prefix="/api/v1/company", tags=["company-analytics"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-analytics"])


@router.post("/events", response_model=AnalyticsEventAccepted, status_code=status.HTTP_202_ACCEPTED)
def collect_events(
    payload: AnalyticsEventBatch,
    request: Request,
    current_user: OptionalCurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    accepted = AnalyticsEventService.collect(
        session,
        payload=payload,
        user=current_user,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    return {"accepted": accepted}


def _period(date_from: date | None, date_to: date | None, interval: str) -> tuple[date, date, str]:
    try:
        return AnalyticsReportService.resolve_period(date_from, date_to, interval)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@company_router.get("/analytics", response_model=AnalyticsReport)
def company_analytics(
    current_user: CurrentUser,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    interval: str = Query(default="auto"),
    session: Session = Depends(get_db),
) -> dict:
    if current_user["role"] != "company":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="업체 권한이 필요합니다.")
    company_id = repository.find_company_for_user(session, int(current_user["id"]))
    if company_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="소속 업체를 찾을 수 없습니다.")
    start, end, resolved_interval = _period(date_from, date_to, interval)
    return AnalyticsReportService.build(
        session,
        date_from=start,
        date_to=end,
        interval=resolved_interval,
        scope="company",
        company_id=company_id,
    )


@admin_router.get("/analytics", response_model=AnalyticsReport)
def admin_analytics(
    current_admin: CurrentAdmin,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    interval: str = Query(default="auto"),
    company_id: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db),
) -> dict:
    del current_admin
    start, end, resolved_interval = _period(date_from, date_to, interval)
    return AnalyticsReportService.build(
        session,
        date_from=start,
        date_to=end,
        interval=resolved_interval,
        scope="admin",
        company_id=company_id,
    )
