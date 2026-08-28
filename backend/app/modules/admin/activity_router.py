from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin import activity_service as service
from app.modules.admin.activity_repository import SEARCHABLE_ACTION_TYPES
from app.modules.admin.activity_schemas import ActivityLogResponse, ActivitySummaryResponse

router = APIRouter(prefix="/api/v1/admin/activity", tags=["admin-activity"])


@router.get("/summary", response_model=ActivitySummaryResponse)
def get_activity_summary(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
    on_date: date | None = Query(default=None),
) -> dict:
    # on_date가 오면 그 날짜 하루치만, 없으면 기존처럼 최근 days일.
    return service.get_summary(session, days=days, on_date=on_date)


@router.get("/log", response_model=ActivityLogResponse)
def get_activity_log(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
    action_type: list[str] | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    action_types = [t for t in action_type if t in SEARCHABLE_ACTION_TYPES] if action_type else None
    from_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    # date_to는 "그 날짜까지 포함"이 되도록 다음날 0시 미만으로 처리.
    to_dt = datetime.combine(date_to, time.min, tzinfo=timezone.utc) + timedelta(days=1) if date_to else None
    return service.search_log(
        session,
        action_types=action_types,
        keyword=keyword,
        date_from=from_dt,
        date_to=to_dt,
        limit=limit,
        offset=offset,
    )
