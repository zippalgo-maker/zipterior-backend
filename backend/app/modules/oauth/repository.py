"""v2.5.57(2026-08-24): SNS 로그인 계정 연결(user_oauth_accounts 테이블,
마이그레이션 a25000000009) 조회/생성과, SNS로 처음 로그인한 사람의
customer 계정 자동 생성을 담당한다. auth/repository.py와 동일하게
raw SQL(text())을 쓴다(이 프로젝트 전체가 ORM 모델 대신 이 방식).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.auth.repository import USER_COLUMNS, find_user_by_email, find_user_by_id


def find_oauth_account(
    session: Session,
    *,
    provider: str,
    provider_user_id: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, user_id, provider, provider_user_id, email
            FROM user_oauth_accounts
            WHERE provider = :provider
              AND provider_user_id = :provider_user_id
            LIMIT 1
            """
        ),
        {"provider": provider, "provider_user_id": provider_user_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def link_oauth_account(
    session: Session,
    *,
    user_id: int,
    provider: str,
    provider_user_id: str,
    email: str | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO user_oauth_accounts (user_id, provider, provider_user_id, email)
            VALUES (:user_id, :provider, :provider_user_id, :email)
            ON CONFLICT (provider, provider_user_id) DO UPDATE
                SET email = EXCLUDED.email, updated_at = NOW()
            """
        ),
        {
            "user_id": user_id,
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
        },
    )


def create_oauth_customer(
    session: Session,
    *,
    email: str,
    name: str,
) -> dict[str, Any]:
    """비밀번호 없이(password_hash NULL) 고객 계정을 새로 만든다 --
    마이그레이션 a25000000009에서 users.password_hash를 nullable로
    바꿔서 가능해짐. 이메일로 로그인/비밀번호 찾기 흐름은 이 계정에
    적용되지 않는다(SNS로만 로그인 가능 -- 준 규칙, 나중에 "비밀번호
    설정" 기능이 필요해지면 별도로 추가)."""
    row = session.execute(
        text(
            f"""
            INSERT INTO users (email, password_hash, name, role, status, marketing_agreed)
            VALUES (:email, NULL, :name, 'customer', 'active', false)
            RETURNING {USER_COLUMNS}
            """
        ),
        {"email": email, "name": name},
    ).mappings().one()
    return dict(row)


__all__ = [
    "find_oauth_account",
    "link_oauth_account",
    "create_oauth_customer",
    "find_user_by_email",
    "find_user_by_id",
]
