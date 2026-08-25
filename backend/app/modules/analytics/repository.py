from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def resolve_entity(
    session: Session,
    *,
    entity_type: str,
    entity_id: int | None,
) -> dict[str, int | None]:
    """Resolve ownership from DB; client-provided company ownership is never trusted."""
    result: dict[str, int | None] = {
        "company_id": None,
        "portfolio_id": None,
        "complex_id": None,
    }
    if entity_id is None:
        return result
    if entity_type == "company":
        exists = session.execute(
            text("SELECT id FROM companies WHERE id=:id AND deleted_at IS NULL"),
            {"id": entity_id},
        ).scalar_one_or_none()
        result["company_id"] = int(exists) if exists else None
    elif entity_type == "portfolio":
        row = session.execute(
            text(
                "SELECT id,company_id FROM portfolios "
                "WHERE id=:id AND deleted_at IS NULL"
            ),
            {"id": entity_id},
        ).mappings().one_or_none()
        if row:
            result["portfolio_id"] = int(row["id"])
            result["company_id"] = int(row["company_id"])
    elif entity_type == "complex":
        # 단지 테이블은 deleted_at을 사용하지 않고 is_active로 공개 상태를 관리한다.
        # 존재하지 않는 컬럼을 조회하던 이전 조건을 실제 스키마 기준으로 대체해
        # 단지 선택 이벤트가 분석 수집 전체를 rollback하지 않도록 한다.
        exists = session.execute(
            text("SELECT id FROM apartment_complexes WHERE id=:id AND is_active=TRUE"),
            {"id": entity_id},
        ).scalar_one_or_none()
        result["complex_id"] = int(exists) if exists else None
    return result


def insert_event(session: Session, values: dict[str, Any]) -> bool:
    inserted = session.execute(
        text(
            """
            INSERT INTO analytics_events (
                client_event_id,session_id,user_id,company_id,portfolio_id,
                complex_id,event_type,duration_seconds,search_query,page_path,
                referrer,traffic_source,browser,operating_system,device_type,metadata
            ) VALUES (
                :client_event_id,:session_id,:user_id,:company_id,:portfolio_id,
                :complex_id,:event_type,:duration_seconds,:search_query,:page_path,
                :referrer,:traffic_source,:browser,:operating_system,:device_type,
                CAST(:metadata AS JSONB)
            )
            ON CONFLICT (client_event_id) DO NOTHING
            RETURNING id
            """
        ),
        values,
    ).scalar_one_or_none()
    return inserted is not None


def find_company_for_user(session: Session, user_id: int) -> int | None:
    value = session.execute(
        text(
            """
            SELECT cm.company_id
            FROM company_members cm
            JOIN companies c ON c.id=cm.company_id AND c.deleted_at IS NULL
            WHERE cm.user_id=:user_id AND cm.status='active'
            ORDER BY CASE cm.member_role WHEN 'owner' THEN 0 ELSE 1 END
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).scalar_one_or_none()
    return int(value) if value is not None else None


def _scope_clause(company_id: int | None) -> tuple[str, dict[str, Any]]:
    if company_id is None:
        return "", {}
    return " AND ae.company_id=:company_id", {"company_id": company_id}


def report_summary(
    session: Session,
    *,
    date_from: date,
    date_to: date,
    company_id: int | None,
) -> dict[str, Any]:
    scope, params = _scope_clause(company_id)
    params.update({"date_from": date_from, "date_to": date_to})
    row = session.execute(
        text(
            f"""
            SELECT
              COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS sessions,
              COUNT(*) FILTER (WHERE event_type='page_view') AS page_views,
              COUNT(*) FILTER (WHERE event_type='company_view') AS company_views,
              COUNT(*) FILTER (WHERE event_type='portfolio_view') AS portfolio_views,
              COALESCE(SUM(duration_seconds) FILTER (WHERE event_type='company_dwell'),0) AS company_dwell_seconds,
              COALESCE(SUM(duration_seconds) FILTER (WHERE event_type='portfolio_dwell'),0) AS portfolio_dwell_seconds,
              COALESCE(ROUND(AVG(duration_seconds) FILTER (WHERE event_type='company_dwell')),0) AS average_company_dwell_seconds,
              COALESCE(ROUND(AVG(duration_seconds) FILTER (WHERE event_type='portfolio_dwell')),0) AS average_portfolio_dwell_seconds,
              COUNT(*) FILTER (WHERE event_type IN ('company_favorite_add','portfolio_favorite_add','portfolio_like_add')) AS engagement_adds,
              COUNT(*) FILTER (WHERE event_type IN ('company_favorite_remove','portfolio_favorite_remove','portfolio_like_remove')) AS engagement_removes,
              COUNT(*) FILTER (WHERE event_type='search') AS searches,
              COUNT(*) FILTER (WHERE event_type='inquiry_submit') AS inquiries
            FROM analytics_events ae
            WHERE ae.occurred_at >= CAST(:date_from AS DATE)
              AND ae.occurred_at < CAST(:date_to AS DATE) + INTERVAL '1 day'
              {scope}
            """
        ),
        params,
    ).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def report_series(
    session: Session,
    *,
    date_from: date,
    date_to: date,
    interval: str,
    company_id: int | None,
) -> list[dict[str, Any]]:
    scope, params = _scope_clause(company_id)
    params.update({"date_from": date_from, "date_to": date_to, "interval": interval})
    rows = session.execute(
        text(
            f"""
            SELECT TO_CHAR(DATE_TRUNC(:interval,ae.occurred_at),
                    CASE :interval WHEN 'month' THEN 'YYYY-MM' ELSE 'YYYY-MM-DD' END) AS label,
              COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS sessions,
              COUNT(*) FILTER (WHERE event_type='company_view') AS company_views,
              COUNT(*) FILTER (WHERE event_type='portfolio_view') AS portfolio_views,
              COALESCE(SUM(duration_seconds) FILTER (WHERE event_type IN ('company_dwell','portfolio_dwell')),0) AS dwell_seconds,
              COUNT(*) FILTER (WHERE event_type IN ('company_favorite_add','portfolio_favorite_add','portfolio_like_add')) AS engagement_adds,
              COUNT(*) FILTER (WHERE event_type IN ('company_favorite_remove','portfolio_favorite_remove','portfolio_like_remove')) AS engagement_removes,
              COUNT(*) FILTER (WHERE event_type='search') AS searches
            FROM analytics_events ae
            WHERE ae.occurred_at >= CAST(:date_from AS DATE)
              AND ae.occurred_at < CAST(:date_to AS DATE) + INTERVAL '1 day'
              {scope}
            GROUP BY DATE_TRUNC(:interval,ae.occurred_at)
            ORDER BY DATE_TRUNC(:interval,ae.occurred_at)
            """
        ),
        params,
    ).mappings().all()
    return [
        {key: (int(value or 0) if key != "label" else value) for key, value in row.items()}
        for row in rows
    ]


def report_content(
    session: Session,
    *,
    date_from: date,
    date_to: date,
    company_id: int | None,
) -> list[dict[str, Any]]:
    scope, params = _scope_clause(company_id)
    params.update({"date_from": date_from, "date_to": date_to})
    rows = session.execute(
        text(
            f"""
            WITH content_events AS (
              SELECT ae.*,
                CASE WHEN ae.portfolio_id IS NOT NULL THEN 'portfolio' ELSE 'company' END AS entity_type,
                COALESCE(ae.portfolio_id,ae.company_id) AS entity_id
              FROM analytics_events ae
              WHERE ae.occurred_at >= CAST(:date_from AS DATE)
                AND ae.occurred_at < CAST(:date_to AS DATE) + INTERVAL '1 day'
                AND (ae.portfolio_id IS NOT NULL OR ae.company_id IS NOT NULL)
                {scope}
            )
            SELECT ce.entity_type,ce.entity_id,
              CASE WHEN ce.entity_type='portfolio' THEN MAX(p.title) ELSE MAX(c.name) END AS title,
              COUNT(*) FILTER (WHERE ce.event_type IN ('company_view','portfolio_view')) AS views,
              COALESCE(SUM(ce.duration_seconds) FILTER (WHERE ce.event_type IN ('company_dwell','portfolio_dwell')),0) AS dwell_seconds,
              COUNT(*) FILTER (WHERE ce.event_type IN ('company_favorite_add','portfolio_favorite_add','portfolio_like_add')) AS engagement_adds,
              COUNT(*) FILTER (WHERE ce.event_type IN ('company_favorite_remove','portfolio_favorite_remove','portfolio_like_remove')) AS engagement_removes
            FROM content_events ce
            LEFT JOIN portfolios p ON ce.entity_type='portfolio' AND p.id=ce.entity_id
            LEFT JOIN companies c ON ce.entity_type='company' AND c.id=ce.entity_id
            GROUP BY ce.entity_type,ce.entity_id
            ORDER BY views DESC,dwell_seconds DESC
            LIMIT 30
            """
        ),
        params,
    ).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        item.update({key: int(item[key] or 0) for key in ("entity_id", "views", "dwell_seconds", "engagement_adds", "engagement_removes")})
        item["title"] = item["title"] or f"삭제된 {item['entity_type']} #{item['entity_id']}"
        item["href"] = f"/?openPortfolio={item['entity_id']}" if item["entity_type"] == "portfolio" else f"/?openCompany={item['entity_id']}"
        result.append(item)
    return result


def report_rank(
    session: Session,
    *,
    column: str,
    date_from: date,
    date_to: date,
    company_id: int | None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    allowed = {"search_query", "traffic_source", "browser", "operating_system", "device_type"}
    if column not in allowed:
        raise ValueError("Unsupported analytics rank column")
    scope, params = _scope_clause(company_id)
    event_clause = ""
    if event_type:
        event_clause = " AND ae.event_type=:event_type"
        params["event_type"] = event_type
    params.update({"date_from": date_from, "date_to": date_to})
    rows = session.execute(
        text(
            f"""
            SELECT COALESCE(NULLIF(ae.{column},''),'직접/알 수 없음') AS label,COUNT(*) AS count
            FROM analytics_events ae
            WHERE ae.occurred_at >= CAST(:date_from AS DATE)
              AND ae.occurred_at < CAST(:date_to AS DATE) + INTERVAL '1 day'
              AND ae.{column} IS NOT NULL
              {event_clause} {scope}
            GROUP BY COALESCE(NULLIF(ae.{column},''),'직접/알 수 없음')
            ORDER BY count DESC,label
            LIMIT 20
            """
        ),
        params,
    ).mappings().all()
    return [{"label": row["label"], "count": int(row["count"])} for row in rows]


def recent_engagement(
    session: Session,
    *,
    date_from: date,
    date_to: date,
    company_id: int | None,
) -> list[dict[str, Any]]:
    scope, params = _scope_clause(company_id)
    params.update({"date_from": date_from, "date_to": date_to})
    rows = session.execute(
        text(
            f"""
            SELECT ae.occurred_at,ae.event_type,
              CASE WHEN ae.portfolio_id IS NOT NULL THEN 'portfolio' ELSE 'company' END AS entity_type,
              COALESCE(ae.portfolio_id,ae.company_id) AS entity_id,
              COALESCE(p.title,c.name,'삭제된 콘텐츠') AS title
            FROM analytics_events ae
            LEFT JOIN portfolios p ON p.id=ae.portfolio_id
            LEFT JOIN companies c ON c.id=ae.company_id AND ae.portfolio_id IS NULL
            WHERE ae.occurred_at >= CAST(:date_from AS DATE)
              AND ae.occurred_at < CAST(:date_to AS DATE) + INTERVAL '1 day'
              AND ae.event_type IN (
                'company_favorite_add','company_favorite_remove',
                'portfolio_favorite_add','portfolio_favorite_remove',
                'portfolio_like_add','portfolio_like_remove'
              ) {scope}
            ORDER BY ae.occurred_at DESC LIMIT 50
            """
        ),
        params,
    ).mappings().all()
    result = []
    for row in rows:
        entity_id = int(row["entity_id"])
        entity_type = row["entity_type"]
        result.append({
            "occurred_at": row["occurred_at"].isoformat(),
            "action": row["event_type"],
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": row["title"],
            "href": f"/?openPortfolio={entity_id}" if entity_type == "portfolio" else f"/?openCompany={entity_id}",
        })
    return result
