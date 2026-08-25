from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_company(
    session: Session,
    company_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                c.id,
                c.owner_user_id,
                c.name,
                c.status,
                c.approved_by,
                c.approved_at,
                u.email AS owner_email,
                u.status AS owner_status
            FROM companies AS c
            JOIN users AS u
              ON u.id = c.owner_user_id
            WHERE c.id = :company_id
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def approve_company(
    session: Session,
    *,
    company_id: int,
    owner_user_id: int,
    admin_user_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE companies
            SET status = 'active',
                approved_by = :admin_user_id,
                approved_at = NOW(),
                updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {
            "company_id": company_id,
            "admin_user_id": admin_user_id,
        },
    )

    session.execute(
        text(
            """
            UPDATE users
            SET status = 'active',
                updated_at = NOW()
            WHERE id = :owner_user_id
            """
        ),
        {"owner_user_id": owner_user_id},
    )

    session.execute(
        text(
            """
            UPDATE company_onboarding
            SET status = 'completed',
                updated_at = NOW()
            WHERE company_id = :company_id
            """
        ),
        {"company_id": company_id},
    )


def reject_company(
    session: Session,
    *,
    company_id: int,
    owner_user_id: int,
    reason: str,
) -> None:
    session.execute(
        text(
            """
            UPDATE companies
            SET status = 'inactive',
                updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {"company_id": company_id},
    )

    session.execute(
        text(
            """
            UPDATE users
            SET status = 'withdrawn',
                updated_at = NOW()
            WHERE id = :owner_user_id
            """
        ),
        {"owner_user_id": owner_user_id},
    )

    session.execute(
        text(
            """
            UPDATE company_onboarding
            SET status = 'declined',
                notes = CASE
                    WHEN notes IS NULL OR notes = '' THEN :reason
                    ELSE notes || E'\n[반려] ' || :reason
                END,
                updated_at = NOW()
            WHERE company_id = :company_id
            """
        ),
        {
            "company_id": company_id,
            "reason": reason,
        },
    )


def suspend_company(
    session: Session,
    *,
    company_id: int,
    owner_user_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE companies
            SET status = 'suspended',
                updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {"company_id": company_id},
    )

    session.execute(
        text(
            """
            UPDATE users
            SET status = 'suspended',
                updated_at = NOW()
            WHERE id = :owner_user_id
            """
        ),
        {"owner_user_id": owner_user_id},
    )


def revoke_owner_refresh_tokens(
    session: Session,
    owner_user_id: int,
    reason: str,
) -> int:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :owner_user_id
              AND revoked_at IS NULL
            """
        ),
        {
            "owner_user_id": owner_user_id,
            "reason": reason,
        },
    )

    return int(result.rowcount or 0)
