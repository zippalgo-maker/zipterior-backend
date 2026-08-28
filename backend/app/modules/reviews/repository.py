"""v1.10.1(2026-08-26): reviews 모듈 최초 구현. 이 프로젝트 컨벤션대로
ORM 모델 없이 raw SQL(text())만 쓴다 -- models.py는 계속 0바이트로 둔다."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_review_by_estimate(session: Session, *, estimate_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text("SELECT * FROM reviews WHERE estimate_request_id=:eid"),
        {"eid": estimate_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def create_review(
    session: Session, *, estimate_id: int, customer_id: int, company_id: int,
    portfolio_id: int | None, rating: int, content: str | None,
) -> dict[str, Any]:
    row = session.execute(
        text(
            "INSERT INTO reviews(estimate_request_id, customer_id, company_id, portfolio_id, rating, content) "
            "VALUES (:eid, :cust, :comp, :pf, :rating, :content) "
            "RETURNING id, estimate_request_id, customer_id, company_id, portfolio_id, rating, content, created_at"
        ),
        {"eid": estimate_id, "cust": customer_id, "comp": company_id, "pf": portfolio_id, "rating": rating, "content": content},
    ).mappings().one()
    session.commit()
    return dict(row)


def list_reviews_by_company(session: Session, *, company_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            "SELECT r.*, c.name AS company_name FROM reviews r "
            "JOIN companies c ON c.id=r.company_id "
            "WHERE r.company_id=:cid ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset"
        ),
        {"cid": company_id, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(row) for row in rows]


def count_reviews_by_company(session: Session, *, company_id: int) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM reviews WHERE company_id=:cid"), {"cid": company_id}).scalar_one())


def list_reviews_mine(session: Session, *, customer_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            "SELECT r.*, c.name AS company_name FROM reviews r "
            "JOIN companies c ON c.id=r.company_id "
            "WHERE r.customer_id=:cust ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset"
        ),
        {"cust": customer_id, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(row) for row in rows]


def count_reviews_mine(session: Session, *, customer_id: int) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM reviews WHERE customer_id=:cust"), {"cust": customer_id}).scalar_one())
