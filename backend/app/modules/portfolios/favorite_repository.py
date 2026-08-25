from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_public_favorite_target(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id
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


def has_favorite(
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
                    FROM portfolio_favorites
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


def create_favorite(
    session: Session,
    *,
    user_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            INSERT INTO portfolio_favorites (
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


def delete_favorite(
    session: Session,
    *,
    user_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            DELETE FROM portfolio_favorites
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


def count_user_favorites(
    session: Session,
    *,
    user_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM portfolio_favorites AS pf
                JOIN portfolios AS p
                  ON p.id = pf.portfolio_id
                JOIN companies AS c
                  ON c.id = p.company_id
                WHERE pf.user_id = :user_id
                  AND p.status = 'approved'
                  AND p.deleted_at IS NULL
                  AND c.status = 'active'
                  AND c.is_visible_on_map = TRUE
                """
            ),
            {"user_id": user_id},
        ).scalar_one()
    )


def list_user_favorites(
    session: Session,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                pf.created_at AS favorited_at,

                p.id,
                p.title,
                p.summary,

                p.company_id,
                c.name AS company_name,
                c.logo_path AS company_logo_path,
                c.phone AS company_phone,
                c.sido AS company_sido,
                c.sigungu AS company_sigungu,
                c.eupmyeondong AS company_eupmyeondong,
                c.consultation_available,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name AS apartment_type_name,
                apt.pyeong_label,

                p.construction_scope,
                p.budget_min,
                p.budget_max,
                p.construction_days,
                p.construction_date,

                p.representative_image_id,
                pi.large_path
                    AS representative_large_path,
                pi.medium_path
                    AS representative_medium_path,
                pi.thumbnail_path
                    AS representative_thumbnail_path,

                p.view_count,
                p.like_count,
                p.comment_count,
                p.published_at
            FROM portfolio_favorites AS pf
            JOIN portfolios AS p
              ON p.id = pf.portfolio_id
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            WHERE pf.user_id = :user_id
              AND p.status = 'approved'
              AND p.deleted_at IS NULL
              AND c.status = 'active'
              AND c.is_visible_on_map = TRUE
            ORDER BY pf.created_at DESC, p.id DESC
            LIMIT :limit
            OFFSET :offset
            """
        ),
        {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]
