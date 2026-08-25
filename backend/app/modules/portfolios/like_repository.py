from sqlalchemy import text
from sqlalchemy.orm import Session


def find_public_portfolio_like_target(
    session: Session,
    *,
    portfolio_id: int,
) -> dict | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                p.like_count
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


def has_portfolio_like(
    session: Session,
    *,
    user_id: int,
    portfolio_id: int,
) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM portfolio_likes
                    WHERE user_id = :user_id
                      AND portfolio_id = :portfolio_id
                )
                """
            ),
            {
                "user_id": user_id,
                "portfolio_id": portfolio_id,
            },
        ).scalar_one()
    )


def create_portfolio_like(
    session: Session,
    *,
    user_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            INSERT INTO portfolio_likes (
                user_id,
                portfolio_id
            )
            VALUES (
                :user_id,
                :portfolio_id
            )
            ON CONFLICT (user_id, portfolio_id)
            DO NOTHING
            """
        ),
        {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def delete_portfolio_like(
    session: Session,
    *,
    user_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            DELETE FROM portfolio_likes
            WHERE user_id = :user_id
              AND portfolio_id = :portfolio_id
            """
        ),
        {
            "user_id": user_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def increment_portfolio_like_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                UPDATE portfolios
                SET like_count = like_count + 1
                WHERE id = :portfolio_id
                  AND status = 'approved'
                  AND deleted_at IS NULL
                RETURNING like_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def decrement_portfolio_like_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                UPDATE portfolios
                SET like_count = GREATEST(
                    like_count - 1,
                    0
                )
                WHERE id = :portfolio_id
                  AND deleted_at IS NULL
                RETURNING like_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def get_portfolio_like_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT like_count
                FROM portfolios
                WHERE id = :portfolio_id
                  AND deleted_at IS NULL
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )
