import hashlib
import hmac
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import view_repository


DUPLICATE_VIEW_MINUTES = 30
MAX_SESSION_ID_LENGTH = 200
MAX_USER_AGENT_LENGTH = 500


def normalize_session_id(
    session_id: str | None,
) -> str | None:
    if session_id is None:
        return None

    value = session_id.strip()

    if not value:
        return None

    return value[:MAX_SESSION_ID_LENGTH]


def make_visitor_hash(
    *,
    client_ip: str,
    user_agent: str,
) -> str:
    source = (
        f"{client_ip}|"
        f"{user_agent[:MAX_USER_AGENT_LENGTH]}"
    )

    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        source.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class PublicPortfolioViewService:
    @staticmethod
    def register_view(
        session: Session,
        *,
        portfolio_id: int,
        current_user: dict[str, Any] | None,
        client_ip: str,
        user_agent: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        user_id = (
            int(current_user["id"])
            if current_user is not None
            else None
        )

        normalized_session_id = normalize_session_id(
            session_id
        )

        visitor_hash = None

        if user_id is None:
            visitor_hash = make_visitor_hash(
                client_ip=client_ip,
                user_agent=user_agent,
            )

        is_duplicate = False
        duplicate_basis = None

        if user_id is not None:
            duplicate_basis = "user_id"
            is_duplicate = (
                view_repository.has_recent_user_view(
                    session,
                    portfolio_id=portfolio_id,
                    user_id=user_id,
                    duplicate_minutes=(
                        DUPLICATE_VIEW_MINUTES
                    ),
                )
            )

        elif normalized_session_id is not None:
            duplicate_basis = "session_id"
            is_duplicate = (
                view_repository.has_recent_session_view(
                    session,
                    portfolio_id=portfolio_id,
                    session_id=normalized_session_id,
                    duplicate_minutes=(
                        DUPLICATE_VIEW_MINUTES
                    ),
                )
            )

        elif visitor_hash is not None:
            duplicate_basis = "visitor_hash"
            is_duplicate = (
                view_repository.has_recent_visitor_view(
                    session,
                    portfolio_id=portfolio_id,
                    visitor_hash=visitor_hash,
                    duplicate_minutes=(
                        DUPLICATE_VIEW_MINUTES
                    ),
                )
            )

        if is_duplicate:
            return {
                "counted": False,
                "duplicate": True,
                "duplicate_basis": duplicate_basis,
                "view_count": None,
            }

        try:
            view_event_id = (
                view_repository.create_view_event(
                    session,
                    portfolio_id=portfolio_id,
                    user_id=user_id,
                    visitor_hash=visitor_hash,
                    session_id=normalized_session_id,
                )
            )

            view_count = (
                view_repository
                .increment_portfolio_view_count(
                    session,
                    portfolio_id=portfolio_id,
                )
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioViewed",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "view_event_id": view_event_id,
                    "user_id": user_id,
                    "has_visitor_hash": (
                        visitor_hash is not None
                    ),
                    "has_session_id": (
                        normalized_session_id is not None
                    ),
                    "view_count": view_count,
                },
                metadata={
                    "source": "public_portfolio",
                    "duplicate_window_minutes": (
                        DUPLICATE_VIEW_MINUTES
                    ),
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "counted": True,
            "duplicate": False,
            "duplicate_basis": duplicate_basis,
            "view_count": view_count,
        }
