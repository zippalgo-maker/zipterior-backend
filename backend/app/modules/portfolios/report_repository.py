from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_reportable_comment(
    session: Session,
    *,
    comment_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                pc.id,
                pc.portfolio_id,
                pc.user_id,
                pc.status,
                pc.deleted_at,
                p.company_id
            FROM portfolio_comments AS pc
            JOIN portfolios AS p
              ON p.id = pc.portfolio_id
            JOIN companies AS c
              ON c.id = p.company_id
            WHERE pc.id = :comment_id
              AND pc.status = 'visible'
              AND pc.deleted_at IS NULL
              AND p.status = 'approved'
              AND p.deleted_at IS NULL
              AND c.status = 'active'
              AND c.is_visible_on_map = TRUE
            LIMIT 1
            """
        ),
        {"comment_id": comment_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_existing_report(
    session: Session,
    *,
    reporter_user_id: int,
    comment_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                status
            FROM reports
            WHERE reporter_user_id = :reporter_user_id
              AND target_type = 'portfolio_comment'
              AND target_id = :comment_id
            LIMIT 1
            """
        ),
        {
            "reporter_user_id": reporter_user_id,
            "comment_id": comment_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def create_comment_report(
    session: Session,
    *,
    reporter_user_id: int,
    comment_id: int,
    reason_code: str,
    description: str | None,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO reports (
                reporter_user_id,
                target_type,
                target_id,
                reason_code,
                description,
                status
            )
            VALUES (
                :reporter_user_id,
                'portfolio_comment',
                :comment_id,
                :reason_code,
                :description,
                'received'
            )
            RETURNING
                id,
                reporter_user_id,
                target_type,
                target_id,
                reason_code,
                description,
                status,
                created_at
            """
        ),
        {
            "reporter_user_id": reporter_user_id,
            "comment_id": comment_id,
            "reason_code": reason_code,
            "description": description,
        },
    ).mappings().one()

    return dict(row)
