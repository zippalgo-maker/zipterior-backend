from sqlalchemy import text
from sqlalchemy.orm import Session


def has_recent_user_view(
    session: Session,
    *,
    portfolio_id: int,
    user_id: int,
    duplicate_minutes: int,
) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM portfolio_view_events
                    WHERE portfolio_id = :portfolio_id
                      AND user_id = :user_id
                      AND viewed_at >= (
                          NOW()
                          - make_interval(
                              mins => :duplicate_minutes
                          )
                      )
                )
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "user_id": user_id,
                "duplicate_minutes": duplicate_minutes,
            },
        ).scalar_one()
    )


def has_recent_session_view(
    session: Session,
    *,
    portfolio_id: int,
    session_id: str,
    duplicate_minutes: int,
) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM portfolio_view_events
                    WHERE portfolio_id = :portfolio_id
                      AND session_id = :session_id
                      AND viewed_at >= (
                          NOW()
                          - make_interval(
                              mins => :duplicate_minutes
                          )
                      )
                )
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "session_id": session_id,
                "duplicate_minutes": duplicate_minutes,
            },
        ).scalar_one()
    )


def has_recent_visitor_view(
    session: Session,
    *,
    portfolio_id: int,
    visitor_hash: str,
    duplicate_minutes: int,
) -> bool:
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM portfolio_view_events
                    WHERE portfolio_id = :portfolio_id
                      AND visitor_hash = :visitor_hash
                      AND viewed_at >= (
                          NOW()
                          - make_interval(
                              mins => :duplicate_minutes
                          )
                      )
                )
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "visitor_hash": visitor_hash,
                "duplicate_minutes": duplicate_minutes,
            },
        ).scalar_one()
    )


def create_view_event(
    session: Session,
    *,
    portfolio_id: int,
    user_id: int | None,
    visitor_hash: str | None,
    session_id: str | None,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO portfolio_view_events (
                    portfolio_id,
                    user_id,
                    visitor_hash,
                    session_id
                )
                VALUES (
                    :portfolio_id,
                    :user_id,
                    :visitor_hash,
                    :session_id
                )
                RETURNING id
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "user_id": user_id,
                "visitor_hash": visitor_hash,
                "session_id": session_id,
            },
        ).scalar_one()
    )


def increment_portfolio_view_count(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                UPDATE portfolios
                SET view_count = view_count + 1
                WHERE id = :portfolio_id
                  AND status = 'approved'
                  AND deleted_at IS NULL
                RETURNING view_count
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )
