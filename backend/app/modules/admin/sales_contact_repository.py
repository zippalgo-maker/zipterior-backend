from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def company_exists(session: Session, company_id: int) -> bool:
    row = session.execute(
        text("SELECT 1 FROM companies WHERE id = :company_id AND deleted_at IS NULL"),
        {"company_id": company_id},
    ).scalar_one_or_none()
    return row is not None


def list_sales_contacts(session: Session, company_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT sc.id, sc.company_id, sc.admin_user_id, au.name AS admin_name,
                   sc.content, sc.contacted_at, sc.created_at
            FROM company_sales_contacts sc
            LEFT JOIN users au ON au.id = sc.admin_user_id
            WHERE sc.company_id = :company_id
            ORDER BY sc.contacted_at DESC, sc.id DESC
            """
        ),
        {"company_id": company_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_sales_contact(
    session: Session,
    *,
    company_id: int,
    admin_user_id: int,
    content: str,
    contacted_at: datetime | None,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO company_sales_contacts (
                company_id, admin_user_id, content, contacted_at
            )
            VALUES (
                :company_id, :admin_user_id, :content,
                COALESCE(:contacted_at, NOW())
            )
            RETURNING id, company_id, admin_user_id, content, contacted_at, created_at
            """
        ),
        {
            "company_id": company_id,
            "admin_user_id": admin_user_id,
            "content": content,
            "contacted_at": contacted_at,
        },
    ).mappings().one()

    result = dict(row)
    admin_name = session.execute(
        text("SELECT name FROM users WHERE id = :id"),
        {"id": admin_user_id},
    ).scalar_one_or_none()
    result["admin_name"] = admin_name
    return result
