"""관리자 대시보드 "최근 활동" 위젯 + 검색 가능한 활동 로그의 데이터 접근.
admin_action_logs를 소스로 쓴다(이미 누가/언제/무엇을 했는지 정확히
남고 있으므로 별도 이벤트 테이블을 새로 안 만듦)."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _fetch(
    session: Session,
    *,
    join_sql: str,
    extra_where: str | None,
    action_types: list[str],
    start,
    end,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    # join_sql은 "SELECT ... FROM admin_action_logs l LEFT JOIN ..." 형태(WHERE 없이)만
    # 준다 -- 카테고리별 role 제한(extra_where) + 기간/action_type 필터를 여기서
    # 한 군데서만 이어붙여서 COUNT와 목록이 항상 같은 조건을 보게 한다.
    # start/end: [start, end) 반열린구간(둘 다 tz-aware datetime).
    where = "l.action_type = ANY(:types) AND l.created_at >= :start AND l.created_at < :end"
    if extra_where:
        where += f" AND {extra_where}"
    params = {"types": action_types, "start": start, "end": end, "limit": limit}

    count = session.execute(
        text(f"SELECT COUNT(*) FROM ({join_sql} WHERE {where}) sub"), params
    ).scalar_one()
    rows = session.execute(
        text(f"{join_sql} WHERE {where} ORDER BY l.created_at DESC LIMIT :limit"), params
    ).mappings().all()
    return int(count), [dict(row) for row in rows]


_PORTFOLIO_JOIN = """
    SELECT l.id, l.target_id, l.created_at, l.action_type,
           COALESCE(p.title, '(삭제된 포트폴리오)') AS label,
           p.company_id
    FROM admin_action_logs l
    LEFT JOIN portfolios p ON p.id = l.target_id
"""

_COMPANY_JOIN = """
    SELECT l.id, l.target_id, l.created_at, l.action_type, COALESCE(co.name, '(삭제된 업체)') AS label
    FROM admin_action_logs l
    LEFT JOIN companies co ON co.id = l.target_id
"""

_USER_JOIN = """
    SELECT l.id, l.target_id, l.created_at, l.action_type, COALESCE(u.name, u.email::text, '(삭제된 회원)') AS label
    FROM admin_action_logs l
    LEFT JOIN users u ON u.id = l.target_id
"""
_USER_ONLY_CUSTOMER = "u.role = 'customer'"

_SUSPENDED_JOIN = """
    SELECT l.id, l.target_id, l.created_at, l.action_type, l.reason, l.target_type,
           COALESCE(
             CASE WHEN l.target_type='company' THEN co.name ELSE COALESCE(u2.name, u2.email::text) END,
             '(삭제됨)'
           ) AS label
    FROM admin_action_logs l
    LEFT JOIN companies co ON l.target_type='company' AND co.id = l.target_id
    LEFT JOIN users u2 ON l.target_type='user' AND u2.id = l.target_id
"""


def new_portfolios(session: Session, *, start, end, limit: int = 5):
    return _fetch(session, join_sql=_PORTFOLIO_JOIN, extra_where=None, action_types=["portfolio.created"], start=start, end=end, limit=limit)


def removed_portfolios(session: Session, *, start, end, limit: int = 5):
    return _fetch(
        session, join_sql=_PORTFOLIO_JOIN, extra_where=None,
        action_types=["portfolio.deleted", "portfolio.hidden"], start=start, end=end, limit=limit
    )


def new_companies(session: Session, *, start, end, limit: int = 5):
    return _fetch(session, join_sql=_COMPANY_JOIN, extra_where=None, action_types=["company.self_registered"], start=start, end=end, limit=limit)


def withdrawn_companies(session: Session, *, start, end, limit: int = 5):
    return _fetch(session, join_sql=_COMPANY_JOIN, extra_where=None, action_types=["company.self_withdrawn"], start=start, end=end, limit=limit)


def new_customers(session: Session, *, start, end, limit: int = 5):
    return _fetch(session, join_sql=_USER_JOIN, extra_where=_USER_ONLY_CUSTOMER, action_types=["user.self_registered"], start=start, end=end, limit=limit)


def withdrawn_customers(session: Session, *, start, end, limit: int = 5):
    return _fetch(session, join_sql=_USER_JOIN, extra_where=_USER_ONLY_CUSTOMER, action_types=["user.self_withdrawn"], start=start, end=end, limit=limit)


def suspended(session: Session, *, start, end, limit: int = 5):
    return _fetch(
        session,
        extra_where=None,
        join_sql=_SUSPENDED_JOIN,
        action_types=["user.suspended", "company.suspended"],
        start=start,
        end=end,
        limit=limit,
    )


# ---- 검색 가능한 활동 로그(서버관리 삭제내역과 같은 성격, 전체 이력용) ----
SEARCHABLE_ACTION_TYPES = [
    "portfolio.created", "portfolio.deleted", "portfolio.hidden", "portfolio.unhidden",
    "company.self_registered", "company.self_withdrawn", "company.approved", "company.rejected",
    "company.suspended", "company.unsuspended", "company.suspension_expired",
    "user.self_registered", "user.self_withdrawn", "user.suspended", "user.unsuspended", "user.suspension_expired",
]


def search_activity_log(
    session: Session,
    *,
    action_types: list[str] | None,
    keyword: str | None,
    date_from,
    date_to,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where = ["l.action_type = ANY(:types)"]
    params: dict[str, Any] = {"types": action_types or SEARCHABLE_ACTION_TYPES, "limit": limit, "offset": offset}
    if date_from is not None:
        where.append("l.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where.append("l.created_at < :date_to")
        params["date_to"] = date_to
    if keyword:
        where.append(
            """(
                l.reason ILIKE :kw
                OR COALESCE(co.name,'') ILIKE :kw
                OR COALESCE(u2.name,'') ILIKE :kw
                OR COALESCE(u2.email::text,'') ILIKE :kw
                OR COALESCE(p.title,'') ILIKE :kw
            )"""
        )
        params["kw"] = f"%{keyword}%"
    where_sql = " AND ".join(where)

    base_from = """
        FROM admin_action_logs l
        LEFT JOIN users admin_u ON admin_u.id = l.admin_user_id
        LEFT JOIN companies co ON l.target_type='company' AND co.id = l.target_id
        LEFT JOIN users u2 ON l.target_type='user' AND u2.id = l.target_id
        LEFT JOIN portfolios p ON l.target_type='portfolio' AND p.id = l.target_id
    """

    total = session.execute(text(f"SELECT COUNT(*) {base_from} WHERE {where_sql}"), params).scalar_one()
    rows = session.execute(
        text(
            f"""
            SELECT
              l.id, l.action_type, l.target_type, l.target_id, l.reason, l.created_at,
              COALESCE(admin_u.name, admin_u.email::text, '(본인/시스템)') AS actor_label,
              COALESCE(co.name, u2.name, u2.email::text, p.title) AS target_label
            {base_from}
            WHERE {where_sql}
            ORDER BY l.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return int(total), [dict(row) for row in rows]
