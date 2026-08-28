from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_CONTACT_SELECT = """
    SELECT sc.id, sc.company_id, sc.admin_user_id, au.name AS admin_name,
           sc.content,
           sc.status_code_id, stc.label AS status_label,
           sc.reason_code_id, rsc.label AS reason_label,
           sc.contacted_at, sc.created_at,
           sc.updated_at, sc.updated_by, uu.name AS updated_by_name,
           sc.update_reason,
           (SELECT COUNT(*) FROM sales_contact_edits e WHERE e.contact_id = sc.id) AS edit_count
    FROM company_sales_contacts sc
    LEFT JOIN users au ON au.id = sc.admin_user_id
    LEFT JOIN users uu ON uu.id = sc.updated_by
    LEFT JOIN sales_contact_codes stc ON stc.id = sc.status_code_id
    LEFT JOIN sales_contact_codes rsc ON rsc.id = sc.reason_code_id
"""


def company_exists(session: Session, company_id: int) -> bool:
    row = session.execute(
        text("SELECT 1 FROM companies WHERE id = :company_id AND deleted_at IS NULL"),
        {"company_id": company_id},
    ).scalar_one_or_none()
    return row is not None


def list_codes(session: Session, code_type: str | None = None) -> list[dict[str, Any]]:
    where = ["is_active = TRUE"]
    params: dict[str, Any] = {}
    if code_type:
        where.append("code_type = :code_type")
        params["code_type"] = code_type
    clause = " AND ".join(where)
    rows = session.execute(
        text(
            f"""
            SELECT id, code_type, label, sort_order, is_active
            FROM sales_contact_codes
            WHERE {clause}
            ORDER BY code_type, sort_order, id
            """
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def create_code(session: Session, *, code_type: str, label: str) -> dict[str, Any]:
    next_sort = session.execute(
        text(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM sales_contact_codes WHERE code_type = :code_type"
        ),
        {"code_type": code_type},
    ).scalar_one()
    row = session.execute(
        text(
            """
            INSERT INTO sales_contact_codes (code_type, label, sort_order)
            VALUES (:code_type, :label, :sort_order)
            RETURNING id, code_type, label, sort_order, is_active
            """
        ),
        {"code_type": code_type, "label": label, "sort_order": next_sort},
    ).mappings().one()
    return dict(row)


def list_sales_contacts(
    session: Session,
    company_id: int,
    *,
    admin_user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    weekday: int | None = None,
    q: str | None = None,
    sort: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where = ["sc.company_id = :company_id"]
    params: dict[str, Any] = {"company_id": company_id, "limit": limit, "offset": offset}
    if admin_user_id:
        where.append("sc.admin_user_id = :admin_user_id")
        params["admin_user_id"] = admin_user_id
    if date_from:
        where.append("sc.contacted_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("sc.contacted_at < (:date_to::date + INTERVAL '1 day')")
        params["date_to"] = date_to
    if weekday is not None:
        where.append("EXTRACT(DOW FROM sc.contacted_at) = :weekday")
        params["weekday"] = weekday
    if q:
        where.append(
            "(sc.content ILIKE :q OR COALESCE(au.name,'') ILIKE :q "
            "OR COALESCE(stc.label,'') ILIKE :q OR COALESCE(rsc.label,'') ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    clause = " AND ".join(where)
    order = "ASC" if sort == "asc" else "DESC"

    total = int(
        session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM company_sales_contacts sc
                LEFT JOIN users au ON au.id = sc.admin_user_id
                LEFT JOIN sales_contact_codes stc ON stc.id = sc.status_code_id
                LEFT JOIN sales_contact_codes rsc ON rsc.id = sc.reason_code_id
                WHERE {clause}
                """
            ),
            params,
        ).scalar_one()
    )
    rows = session.execute(
        text(f"{_CONTACT_SELECT} WHERE {clause} ORDER BY sc.contacted_at {order}, sc.id {order} LIMIT :limit OFFSET :offset"),
        params,
    ).mappings().all()
    return [dict(r) for r in rows], total


def get_sales_contact(session: Session, contact_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(f"{_CONTACT_SELECT} WHERE sc.id = :contact_id"),
        {"contact_id": contact_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def create_sales_contact(
    session: Session,
    *,
    company_id: int,
    admin_user_id: int,
    content: str,
    contacted_at: datetime | None,
    status_code_id: int | None,
    reason_code_id: int | None,
) -> int:
    contact_id = session.execute(
        text(
            """
            INSERT INTO company_sales_contacts (
                company_id, admin_user_id, content, contacted_at,
                status_code_id, reason_code_id
            )
            VALUES (
                :company_id, :admin_user_id, :content, COALESCE(:contacted_at, NOW()),
                :status_code_id, :reason_code_id
            )
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "admin_user_id": admin_user_id,
            "content": content,
            "contacted_at": contacted_at,
            "status_code_id": status_code_id,
            "reason_code_id": reason_code_id,
        },
    ).scalar_one()
    return int(contact_id)


def update_sales_contact(
    session: Session,
    *,
    contact_id: int,
    admin_user_id: int,
    content: str,
    status_code_id: int | None,
    reason_code_id: int | None,
    contacted_at: datetime | None,
    reason: str,
) -> None:
    previous = session.execute(
        text(
            """
            SELECT content, status_code_id, reason_code_id
            FROM company_sales_contacts
            WHERE id = :id
            FOR UPDATE
            """
        ),
        {"id": contact_id},
    ).mappings().one()

    session.execute(
        text(
            """
            INSERT INTO sales_contact_edits (
                contact_id, edited_by, reason,
                previous_content, previous_status_code_id, previous_reason_code_id
            )
            VALUES (
                :contact_id, :edited_by, :reason,
                :previous_content, :previous_status_code_id, :previous_reason_code_id
            )
            """
        ),
        {
            "contact_id": contact_id,
            "edited_by": admin_user_id,
            "reason": reason,
            "previous_content": previous["content"],
            "previous_status_code_id": previous["status_code_id"],
            "previous_reason_code_id": previous["reason_code_id"],
        },
    )

    session.execute(
        text(
            """
            UPDATE company_sales_contacts
            SET content = :content,
                status_code_id = :status_code_id,
                reason_code_id = :reason_code_id,
                contacted_at = COALESCE(:contacted_at, contacted_at),
                updated_at = NOW(),
                updated_by = :updated_by,
                update_reason = :update_reason
            WHERE id = :id
            """
        ),
        {
            "id": contact_id,
            "content": content,
            "status_code_id": status_code_id,
            "reason_code_id": reason_code_id,
            "contacted_at": contacted_at,
            "updated_by": admin_user_id,
            "update_reason": reason,
        },
    )


def list_edits(session: Session, contact_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT e.id, e.edited_by, eu.name AS edited_by_name, e.edited_at, e.reason,
                   e.previous_content,
                   stc.label AS previous_status_label,
                   rsc.label AS previous_reason_label
            FROM sales_contact_edits e
            LEFT JOIN users eu ON eu.id = e.edited_by
            LEFT JOIN sales_contact_codes stc ON stc.id = e.previous_status_code_id
            LEFT JOIN sales_contact_codes rsc ON rsc.id = e.previous_reason_code_id
            WHERE e.contact_id = :contact_id
            ORDER BY e.edited_at DESC, e.id DESC
            """
        ),
        {"contact_id": contact_id},
    ).mappings().all()
    return [dict(r) for r in rows]
