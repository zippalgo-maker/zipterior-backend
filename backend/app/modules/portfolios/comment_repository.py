from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_public_comment_target(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                p.comment_count
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            WHERE p.id = :portfolio_id
              AND p.status = 'approved'
              AND p.deleted_at IS NULL
              AND c.status = 'active'
              AND c.is_visible_on_map = TRUE
            LIMIT 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_comment(
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
                pc.parent_id,
                pc.content,
                pc.status,
                pc.created_at,
                pc.updated_at,
                pc.deleted_at
            FROM portfolio_comments AS pc
            WHERE pc.id = :comment_id
            LIMIT 1
            """
        ),
        {"comment_id": comment_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def count_visible_comments(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM portfolio_comments
                WHERE portfolio_id = :portfolio_id
                  AND status = 'visible'
                  AND deleted_at IS NULL
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def list_visible_comments(
    session: Session,
    *,
    portfolio_id: int,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                pc.id,
                pc.portfolio_id,
                pc.parent_id,
                pc.content,
                pc.status,
                pc.created_at,
                pc.updated_at,

                u.id AS author_id,
                u.name AS author_name,
                u.nickname AS author_nickname
            FROM portfolio_comments AS pc
            JOIN users AS u
              ON u.id = pc.user_id
            WHERE pc.portfolio_id = :portfolio_id
              AND pc.status = 'visible'
              AND pc.deleted_at IS NULL
            ORDER BY
                COALESCE(pc.parent_id, pc.id),
                CASE
                    WHEN pc.parent_id IS NULL THEN 0
                    ELSE 1
                END,
                pc.created_at,
                pc.id
            LIMIT :limit
            OFFSET :offset
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def create_comment(
    session: Session,
    *,
    portfolio_id: int,
    user_id: int,
    parent_id: int | None,
    content: str,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO portfolio_comments (
                portfolio_id,
                user_id,
                parent_id,
                content,
                status
            )
            VALUES (
                :portfolio_id,
                :user_id,
                :parent_id,
                :content,
                'visible'
            )
            RETURNING
                id,
                portfolio_id,
                user_id,
                parent_id,
                content,
                status,
                created_at,
                updated_at
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "user_id": user_id,
            "parent_id": parent_id,
            "content": content,
        },
    ).mappings().one()

    return dict(row)


def update_comment(
    session: Session,
    *,
    comment_id: int,
    user_id: int,
    content: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolio_comments
            SET content = :content,
                updated_at = NOW()
            WHERE id = :comment_id
              AND user_id = :user_id
              AND status = 'visible'
              AND deleted_at IS NULL
            RETURNING
                id,
                portfolio_id,
                user_id,
                parent_id,
                content,
                status,
                created_at,
                updated_at
            """
        ),
        {
            "comment_id": comment_id,
            "user_id": user_id,
            "content": content,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def soft_delete_comment(
    session: Session,
    *,
    comment_id: int,
    user_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolio_comments
            SET status = 'deleted',
                deleted_at = NOW(),
                updated_at = NOW()
            WHERE id = :comment_id
              AND user_id = :user_id
              AND status = 'visible'
              AND deleted_at IS NULL
            RETURNING
                id,
                portfolio_id,
                parent_id
            """
        ),
        {
            "comment_id": comment_id,
            "user_id": user_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


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
                  AND deleted_at IS NULL
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
                  AND deleted_at IS NULL
                RETURNING comment_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def get_comment_author(
    session: Session,
    *,
    user_id: int,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT
                id,
                name,
                nickname
            FROM users
            WHERE id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().one()

    return dict(row)
