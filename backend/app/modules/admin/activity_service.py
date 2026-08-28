from datetime import date as date_cls, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.modules.admin import activity_repository as repository

_KST = ZoneInfo("Asia/Seoul")

# (key, label, color, nav_view, fetch_fn)
_CATEGORY_SPECS = [
    ("new_portfolios", "신규 포트폴리오", "#2b9e5c", "portfolioManageView", repository.new_portfolios),
    ("removed_portfolios", "삭제·노출중지 포트폴리오", "#e0483a", "portfolioManageView", repository.removed_portfolios),
    ("new_companies", "신규 가입 업체", "#2f6fed", "companyManageView", repository.new_companies),
    ("withdrawn_companies", "탈퇴 업체", "#888888", "companyManageView", repository.withdrawn_companies),
    ("new_customers", "신규 가입 회원", "#2f6fed", "memberManageView", repository.new_customers),
    ("withdrawn_customers", "탈퇴 회원", "#888888", "memberManageView", repository.withdrawn_customers),
    ("suspended", "이용정지", "#e0a02a", "memberManageView", repository.suspended),
]


def _resolve_window(days: int, on_date: date_cls | None) -> tuple[datetime, datetime]:
    """on_date가 있으면 그 날짜(한국시간 00:00~24:00) 하루, 없으면 지금부터 days일 전까지."""
    if on_date is not None:
        start = datetime.combine(on_date, time.min, tzinfo=_KST)
        end = start + timedelta(days=1)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end


def get_summary(session: Session, *, days: int, on_date: date_cls | None = None) -> dict[str, Any]:
    start, end = _resolve_window(days, on_date)
    categories = []
    for key, label, color, nav_view, fetch_fn in _CATEGORY_SPECS:
        count, rows = fetch_fn(session, start=start, end=end)
        items = [
            {"id": row["id"], "label": row["label"] or "-", "created_at": row["created_at"], "nav_view": nav_view}
            for row in rows
        ]
        categories.append(
            {"key": key, "label": label, "color": color, "count": count, "nav_view": nav_view, "items": items}
        )
    return {"days": days, "date": on_date.isoformat() if on_date else None, "categories": categories}


def search_log(
    session: Session,
    *,
    action_types: list[str] | None,
    keyword: str | None,
    date_from,
    date_to,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    total, rows = repository.search_activity_log(
        session,
        action_types=action_types,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
