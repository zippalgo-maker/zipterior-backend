from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_password_hash(session: Session, user_id: int) -> str | None:
    return session.execute(
        text("SELECT password_hash FROM users WHERE id=:id"), {"id": user_id}
    ).scalar()


def find_owned_company(session: Session, user_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text("SELECT id, status FROM companies WHERE owner_user_id=:u AND deleted_at IS NULL"),
        {"u": user_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def withdraw_user(session: Session, user_id: int) -> None:
    session.execute(
        text(
            """
            UPDATE users
            SET status='withdrawn', deleted_at=NOW(), updated_at=NOW()
            WHERE id=:id
            """
        ),
        {"id": user_id},
    )


def withdraw_company(session: Session, company_id: int) -> None:
    session.execute(
        text(
            """
            UPDATE companies
            SET status='inactive', updated_at=NOW()
            WHERE id=:id
            """
        ),
        {"id": company_id},
    )


def revoke_all_refresh_tokens(session: Session, user_id: int, reason: str) -> None:
    session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :user_id AND revoked_at IS NULL
            """
        ),
        {"user_id": user_id, "reason": reason},
    )
