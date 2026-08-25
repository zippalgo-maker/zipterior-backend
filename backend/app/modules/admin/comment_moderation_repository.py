from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def count_comment_reports(
    session: Session,
    *,
    report_status: str | None,
) -> int:
    conditions = [
        "r.target_type = 'portfolio_comment'",
    ]
    params: dict[str, Any] = {}

    if report_status is not None:
        conditions.append("r.status = :report_status")
        params["report_status"] = report_status

    return int(
        session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM reports AS r
                WHERE {" AND ".join(conditions)}
                """
            ),
            params,
        ).scalar_one()
    )


def list_comment_reports(
    session: Session,
    *,
    report_status: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    conditions = [
        "r.target_type = 'portfolio_comment'",
    ]
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if report_status is not None:
        conditions.append("r.status = :report_status")
        params["report_status"] = report_status

    rows = session.execute(
        text(
            f"""
            SELECT
                r.id,
                r.reporter_user_id,
                ru.name AS reporter_name,

                r.target_id AS comment_id,
                pc.content AS comment_content,
                pc.status AS comment_status,
                pc.user_id AS comment_user_id,
                pc.portfolio_id,

                r.reason_code,
                r.description,
                r.status,
                r.handled_by,
                r.handled_note,
                r.handled_at,
                r.created_at
            FROM reports AS r
            JOIN portfolio_comments AS pc
              ON pc.id = r.target_id
            LEFT JOIN users AS ru
              ON ru.id = r.reporter_user_id
            WHERE {" AND ".join(conditions)}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT :limit
            OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


def find_comment_report(
    session: Session,
    *,
    report_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                r.id,
                r.target_id AS comment_id,
                r.status,
                r.handled_by,
                r.handled_note,
                r.handled_at
            FROM reports AS r
            WHERE r.id = :report_id
              AND r.target_type = 'portfolio_comment'
            LIMIT 1
            """
        ),
        {"report_id": report_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def review_comment_report(
    session: Session,
    *,
    report_id: int,
    report_status: str,
    admin_user_id: int,
    handled_note: str | None,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE reports
            SET status = :report_status,
                handled_by = :admin_user_id,
                handled_note = :handled_note,
                handled_at = NOW()
            WHERE id = :report_id
              AND target_type = 'portfolio_comment'
            RETURNING
                id,
                status,
                handled_by,
                handled_note,
                handled_at
            """
        ),
        {
            "report_id": report_id,
            "report_status": report_status,
            "admin_user_id": admin_user_id,
            "handled_note": handled_note,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_comment_for_moderation(
    session: Session,
    *,
    comment_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                portfolio_id,
                user_id,
                parent_id,
                content,
                status,
                deleted_at
            FROM portfolio_comments
            WHERE id = :comment_id
            LIMIT 1
            """
        ),
        {"comment_id": comment_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def hide_comment(
    session: Session,
    *,
    comment_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolio_comments
            SET status = 'hidden',
                updated_at = NOW()
            WHERE id = :comment_id
              AND status = 'visible'
              AND deleted_at IS NULL
            """
        ),
        {"comment_id": comment_id},
    )

    return bool(result.rowcount)


def restore_comment(
    session: Session,
    *,
    comment_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolio_comments
            SET status = 'visible',
                updated_at = NOW()
            WHERE id = :comment_id
              AND status = 'hidden'
              AND deleted_at IS NULL
            """
        ),
        {"comment_id": comment_id},
    )

    return bool(result.rowcount)


def increment_comment_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                UPDATE portfolios
                SET comment_count = comment_count + 1
                WHERE id = :portfolio_id
                RETURNING comment_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def decrement_comment_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                UPDATE portfolios
                SET comment_count = GREATEST(
                    comment_count - 1,
                    0
                )
                WHERE id = :portfolio_id
                RETURNING comment_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )
