import json
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.modules.analytics import repository
from app.modules.analytics.schemas import AnalyticsEventBatch


ALLOWED_METADATA_KEYS = {
    "results_count",
    "selected_kind",
    "selected_id",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "screen_width",
}


def _client_environment(user_agent: str) -> tuple[str, str, str]:
    ua = user_agent.lower()
    if "edg/" in ua:
        browser = "Edge"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "chrome/" in ua and "chromium" not in ua:
        browser = "Chrome"
    elif "safari/" in ua and "chrome/" not in ua:
        browser = "Safari"
    elif ua:
        browser = "기타"
    else:
        browser = "알 수 없음"

    if "windows" in ua:
        operating_system = "Windows"
    elif "android" in ua:
        operating_system = "Android"
    elif "iphone" in ua or "ipad" in ua:
        operating_system = "iOS/iPadOS"
    elif "mac os" in ua or "macintosh" in ua:
        operating_system = "macOS"
    elif "linux" in ua:
        operating_system = "Linux"
    else:
        operating_system = "알 수 없음"

    if "tablet" in ua or "ipad" in ua:
        device = "태블릿"
    elif "mobile" in ua or "iphone" in ua or "android" in ua:
        device = "모바일"
    else:
        device = "PC"
    return browser, operating_system, device


def _traffic_source(referrer: str | None, metadata: dict[str, Any]) -> str:
    utm_source = str(metadata.get("utm_source") or "").strip()[:80]
    if utm_source:
        return utm_source
    if not referrer:
        return "직접 접속"
    try:
        host = (urlparse(referrer).hostname or "").lower()
    except ValueError:
        return "기타 유입"
    if not host or host.endswith("zipterior.kr"):
        return "내부 이동"
    engines = {
        "naver.com": "네이버 검색",
        "google.": "구글 검색",
        "daum.net": "다음 검색",
        "bing.com": "빙 검색",
    }
    for part, label in engines.items():
        if part in host:
            return label
    return host[:80]


class AnalyticsEventService:
    @staticmethod
    def collect(
        session: Session,
        *,
        payload: AnalyticsEventBatch,
        user: dict[str, Any] | None,
        user_agent: str,
    ) -> int:
        browser, operating_system, device_type = _client_environment(user_agent)
        accepted = 0
        for event in payload.events:
            entity = repository.resolve_entity(
                session,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
            )
            metadata = {
                key: value
                for key, value in event.metadata.items()
                if key in ALLOWED_METADATA_KEYS
                and isinstance(value, (str, int, float, bool))
            }
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            if len(metadata_json.encode("utf-8")) > 2048:
                metadata_json = "{}"
            values = {
                "client_event_id": event.client_event_id,
                "session_id": event.session_id,
                "user_id": int(user["id"]) if user else None,
                **entity,
                "event_type": event.event_type,
                "duration_seconds": event.duration_seconds,
                "search_query": event.search_query,
                "page_path": event.page_path,
                "referrer": event.referrer,
                "traffic_source": _traffic_source(event.referrer, metadata),
                "browser": browser,
                "operating_system": operating_system,
                "device_type": device_type,
                "metadata": metadata_json,
            }
            if repository.insert_event(session, values):
                accepted += 1
        session.commit()
        return accepted


class AnalyticsReportService:
    @staticmethod
    def resolve_period(
        date_from: date | None,
        date_to: date | None,
        interval: str,
    ) -> tuple[date, date, str]:
        end = date_to or date.today()
        start = date_from or (end - timedelta(days=29))
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if (end - start).days > 730:
            raise ValueError("한 번에 조회할 수 있는 기간은 최대 2년입니다.")
        if interval == "auto":
            days = (end - start).days + 1
            interval = "day" if days <= 62 else "week" if days <= 366 else "month"
        if interval not in {"day", "week", "month"}:
            raise ValueError("지원하지 않는 집계 단위입니다.")
        return start, end, interval

    @staticmethod
    def build(
        session: Session,
        *,
        date_from: date,
        date_to: date,
        interval: str,
        scope: str,
        company_id: int | None,
    ) -> dict[str, Any]:
        args = {
            "date_from": date_from,
            "date_to": date_to,
            "company_id": company_id,
        }
        return {
            "date_from": date_from,
            "date_to": date_to,
            "interval": interval,
            "scope": scope,
            "company_id": company_id,
            "summary": repository.report_summary(session, **args),
            "series": repository.report_series(session, interval=interval, **args),
            "content": repository.report_content(session, **args),
            "search_terms": repository.report_rank(session, column="search_query", event_type="search_select" if company_id else "search", **args),
            "traffic_sources": repository.report_rank(session, column="traffic_source", **args),
            "browsers": repository.report_rank(session, column="browser", **args),
            "operating_systems": repository.report_rank(session, column="operating_system", **args),
            "devices": repository.report_rank(session, column="device_type", **args),
            "recent_engagement": repository.recent_engagement(session, **args),
        }
