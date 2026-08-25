from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def list_active_keywords(
    session: Session,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                name,
                category,
                sort_order
            FROM portfolio_keywords
            WHERE is_active = TRUE
            ORDER BY category, sort_order, id
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


def list_portfolio_keywords(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                pk.id,
                pk.name,
                pk.category,
                pk.sort_order
            FROM portfolio_keyword_links AS pkl
            JOIN portfolio_keywords AS pk
              ON pk.id = pkl.keyword_id
            WHERE pkl.portfolio_id = :portfolio_id
            ORDER BY pk.category, pk.sort_order, pk.id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def find_active_keywords_by_ids(
    session: Session,
    *,
    keyword_ids: list[int],
) -> list[dict[str, Any]]:
    if not keyword_ids:
        return []

    statement = text(
        """
        SELECT
            id,
            name,
            category,
            sort_order
        FROM portfolio_keywords
        WHERE id IN :keyword_ids
          AND is_active = TRUE
        ORDER BY category, sort_order, id
        """
    ).bindparams(
        bindparam(
            "keyword_ids",
            expanding=True,
        )
    )

    rows = session.execute(
        statement,
        {"keyword_ids": keyword_ids},
    ).mappings().all()

    return [dict(row) for row in rows]


def replace_portfolio_keywords(
    session: Session,
    *,
    portfolio_id: int,
    keyword_ids: list[int],
) -> None:
    session.execute(
        text(
            """
            DELETE FROM portfolio_keyword_links
            WHERE portfolio_id = :portfolio_id
            """
        ),
        {"portfolio_id": portfolio_id},
    )

    if not keyword_ids:
        return

    session.execute(
        text(
            """
            INSERT INTO portfolio_keyword_links (
                portfolio_id,
                keyword_id
            )
            VALUES (
                :portfolio_id,
                :keyword_id
            )
            """
        ),
        [
            {
                "portfolio_id": portfolio_id,
                "keyword_id": keyword_id,
            }
            for keyword_id in keyword_ids
        ],
    )
