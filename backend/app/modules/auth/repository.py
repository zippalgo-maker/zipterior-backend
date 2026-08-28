import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


USER_COLUMNS = """
    id,
    email,
    password_hash,
    name,
    nickname,
    phone,
    role,
    status,
    email_verified_at,
    last_login_at,
    marketing_agreed,
    notification_prefs,
    created_at,
    updated_at,
    deleted_at
"""


# v1.10.1(2026-08-26): 알림 설정 화면(목업 15번) -- 견적응답/시공업체댓글/
# 현장사진 3개 토글. 마케팅 토글은 기존 marketing_agreed 그대로 재사용.
def update_user_settings(
    session: Session,
    *,
    user_id: int,
    notification_prefs: dict[str, Any] | None,
    marketing_agreed: bool | None,
) -> dict[str, Any]:
    sets = ["updated_at = NOW()"]
    params: dict[str, Any] = {"user_id": user_id}
    if notification_prefs is not None:
        sets.append("notification_prefs = CAST(:notification_prefs AS jsonb)")
        params["notification_prefs"] = json.dumps(notification_prefs, ensure_ascii=False)
    if marketing_agreed is not None:
        sets.append("marketing_agreed = :marketing_agreed")
        params["marketing_agreed"] = marketing_agreed
    query = text(
        f"""
        UPDATE users
        SET {", ".join(sets)}
        WHERE id = :user_id
        RETURNING {USER_COLUMNS}
        """
    )
    row = session.execute(query, params).mappings().one()
    session.commit()
    return dict(row)


def find_user_by_email(
    session: Session,
    email: str,
) -> dict[str, Any] | None:
    query = text(
        f"""
        SELECT {USER_COLUMNS}
        FROM users
        WHERE email = :email
          AND deleted_at IS NULL
        LIMIT 1
        """
    )

    row = session.execute(
        query,
        {"email": email},
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_user_by_id(
    session: Session,
    user_id: int,
) -> dict[str, Any] | None:
    query = text(
        f"""
        SELECT {USER_COLUMNS}
        FROM users
        WHERE id = :user_id
          AND deleted_at IS NULL
        LIMIT 1
        """
    )

    row = session.execute(
        query,
        {"user_id": user_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def create_customer(
    session: Session,
    *,
    email: str,
    password_hash: str,
    name: str,
    nickname: str | None,
    phone: str | None,
    marketing_agreed: bool,
) -> dict[str, Any]:
    query = text(
        f"""
        INSERT INTO users (
            email,
            password_hash,
            name,
            nickname,
            phone,
            role,
            status,
            marketing_agreed
        )
        VALUES (
            :email,
            :password_hash,
            :name,
            :nickname,
            :phone,
            'customer',
            'active',
            :marketing_agreed
        )
        RETURNING {USER_COLUMNS}
        """
    )

    row = session.execute(
        query,
        {
            "email": email,
            "password_hash": password_hash,
            "name": name,
            "nickname": nickname,
            "phone": phone,
            "marketing_agreed": marketing_agreed,
        },
    ).mappings().one()

    return dict(row)


def update_last_login(
    session: Session,
    user_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE users
            SET last_login_at = NOW(),
                updated_at = NOW()
            WHERE id = :user_id
            """
        ),
        {"user_id": user_id},
    )


def create_refresh_token_record(
    session: Session,
    *,
    user_id: int,
    token_hash: str,
    token_family_id: UUID,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> UUID:
    query = text(
        """
        INSERT INTO auth_refresh_tokens (
            user_id,
            token_hash,
            token_family_id,
            expires_at,
            ip_address,
            user_agent
        )
        VALUES (
            :user_id,
            :token_hash,
            :token_family_id,
            :expires_at,
            CAST(:ip_address AS inet),
            :user_agent
        )
        RETURNING id
        """
    )

    return session.execute(
        query,
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "token_family_id": token_family_id,
            "expires_at": expires_at,
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    ).scalar_one()


def record_login_attempt(
    session: Session,
    *,
    user_id: int | None,
    email: str,
    was_successful: bool,
    failure_reason: str | None,
    ip_address: str | None,
    user_agent: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO auth_login_attempts (
                user_id,
                email,
                was_successful,
                failure_reason,
                ip_address,
                user_agent,
                metadata
            )
            VALUES (
                :user_id,
                :email,
                :was_successful,
                :failure_reason,
                CAST(:ip_address AS inet),
                :user_agent,
                CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "user_id": user_id,
            "email": email,
            "was_successful": was_successful,
            "failure_reason": failure_reason,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": json.dumps(
                metadata or {},
                ensure_ascii=False,
            ),
        },
    )


def find_refresh_token_by_hash(
    session: Session,
    token_hash: str,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT
            id,
            user_id,
            token_hash,
            token_family_id,
            parent_token_id,
            issued_at,
            expires_at,
            last_used_at,
            revoked_at,
            revoke_reason,
            replaced_by_token_id
        FROM auth_refresh_tokens
        WHERE token_hash = :token_hash
        LIMIT 1
        """
    )

    row = session.execute(
        query,
        {"token_hash": token_hash},
    ).mappings().one_or_none()

    return dict(row) if row else None


def rotate_refresh_token(
    session: Session,
    *,
    old_token_id: UUID,
    user_id: int,
    token_hash: str,
    token_family_id: UUID,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> UUID:
    new_token_id = create_refresh_token_record(
        session=session,
        user_id=user_id,
        token_hash=token_hash,
        token_family_id=token_family_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = NOW(),
                revoke_reason = 'rotated',
                replaced_by_token_id = :new_token_id,
                last_used_at = NOW()
            WHERE id = :old_token_id
              AND revoked_at IS NULL
            """
        ),
        {
            "old_token_id": old_token_id,
            "new_token_id": new_token_id,
        },
    )

    return new_token_id


def revoke_refresh_token(
    session: Session,
    token_hash: str,
    reason: str,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE token_hash = :token_hash
            RETURNING id
            """
        ),
        {
            "token_hash": token_hash,
            "reason": reason,
        },
    ).scalar_one_or_none()

    return result is not None


def revoke_token_family(
    session: Session,
    token_family_id: UUID,
    reason: str,
) -> int:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE token_family_id = :token_family_id
              AND revoked_at IS NULL
            """
        ),
        {
            "token_family_id": token_family_id,
            "reason": reason,
        },
    )

    return int(result.rowcount or 0)


def revoke_all_user_tokens(
    session: Session,
    user_id: int,
    reason: str,
) -> int:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :user_id
              AND revoked_at IS NULL
            """
        ),
        {
            "user_id": user_id,
            "reason": reason,
        },
    )

    return int(result.rowcount or 0)


def find_refresh_token_by_hash(
    session: Session,
    token_hash: str,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT
            id,
            user_id,
            token_hash,
            token_family_id,
            parent_token_id,
            issued_at,
            expires_at,
            last_used_at,
            revoked_at,
            revoke_reason,
            replaced_by_token_id
        FROM auth_refresh_tokens
        WHERE token_hash = :token_hash
        LIMIT 1
        """
    )

    row = session.execute(
        query,
        {"token_hash": token_hash},
    ).mappings().one_or_none()

    return dict(row) if row else None


def rotate_refresh_token(
    session: Session,
    *,
    old_token_id: UUID,
    user_id: int,
    token_hash: str,
    token_family_id: UUID,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> UUID:
    new_token_id = create_refresh_token_record(
        session=session,
        user_id=user_id,
        token_hash=token_hash,
        token_family_id=token_family_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = NOW(),
                revoke_reason = 'rotated',
                replaced_by_token_id = :new_token_id,
                last_used_at = NOW()
            WHERE id = :old_token_id
              AND revoked_at IS NULL
            """
        ),
        {
            "old_token_id": old_token_id,
            "new_token_id": new_token_id,
        },
    )

    return new_token_id


def revoke_refresh_token(
    session: Session,
    token_hash: str,
    reason: str,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE token_hash = :token_hash
            RETURNING id
            """
        ),
        {
            "token_hash": token_hash,
            "reason": reason,
        },
    ).scalar_one_or_none()

    return result is not None


def revoke_token_family(
    session: Session,
    token_family_id: UUID,
    reason: str,
) -> int:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE token_family_id = :token_family_id
              AND revoked_at IS NULL
            """
        ),
        {
            "token_family_id": token_family_id,
            "reason": reason,
        },
    )

    return int(result.rowcount or 0)


def revoke_all_user_tokens(
    session: Session,
    user_id: int,
    reason: str,
) -> int:
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :user_id
              AND revoked_at IS NULL
            """
        ),
        {
            "user_id": user_id,
            "reason": reason,
        },
    )

    return int(result.rowcount or 0)
