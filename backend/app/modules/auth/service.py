from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth import repository
from app.modules.auth.schemas import CustomerRegisterRequest, LoginRequest


class EmailAlreadyExistsError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class AccountUnavailableError(ValueError):
    pass


class AuthService:
    @staticmethod
    def register_customer(
        session: Session,
        request: CustomerRegisterRequest,
    ) -> dict[str, Any]:
        existing = repository.find_user_by_email(
            session,
            request.email,
        )

        if existing:
            raise EmailAlreadyExistsError(
                "이미 사용 중인 이메일입니다."
            )

        try:
            user = repository.create_customer(
                session=session,
                email=request.email,
                password_hash=hash_password(request.password),
                name=request.name,
                nickname=request.nickname,
                phone=request.phone,
                marketing_agreed=request.marketing_agreed,
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise EmailAlreadyExistsError(
                "이미 사용 중인 이메일입니다."
            ) from exc

        return user

    @staticmethod
    def login(
        session: Session,
        request: LoginRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        user = repository.find_user_by_email(
            session,
            request.email,
        )

        if user is None or not verify_password(
            request.password,
            user["password_hash"],
        ):
            repository.record_login_attempt(
                session=session,
                user_id=user["id"] if user else None,
                email=request.email,
                was_successful=False,
                failure_reason="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.commit()

            raise InvalidCredentialsError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        if user["status"] != "active":
            repository.record_login_attempt(
                session=session,
                user_id=user["id"],
                email=request.email,
                was_successful=False,
                failure_reason=f"account_{user['status']}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.commit()

            raise AccountUnavailableError(
                "현재 로그인할 수 없는 계정입니다."
            )

        access_token = create_access_token(
            user_id=user["id"],
            role=user["role"],
        )

        refresh_token = create_refresh_token()
        refresh_expire = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

        repository.create_refresh_token_record(
            session=session,
            user_id=user["id"],
            token_hash=hash_token(refresh_token),
            token_family_id=uuid4(),
            expires_at=refresh_expire,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        repository.update_last_login(
            session,
            user["id"],
        )

        repository.record_login_attempt(
            session=session,
            user_id=user["id"],
            email=request.email,
            was_successful=True,
            failure_reason=None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        session.commit()

        refreshed_user = repository.find_user_by_id(
            session,
            user["id"],
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": refreshed_user,
        }


class InvalidRefreshTokenError(ValueError):
    pass


class RefreshTokenReuseError(ValueError):
    pass


def _client_tokens(
    *,
    user: dict[str, Any],
    refresh_token: str,
) -> dict[str, Any]:
    return {
        "access_token": create_access_token(
            user_id=user["id"],
            role=user["role"],
        ),
        "refresh_token": refresh_token,
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": user,
    }


def refresh_login(
    session: Session,
    refresh_token: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    current_hash = hash_token(refresh_token)

    record = repository.find_refresh_token_by_hash(
        session,
        current_hash,
    )

    if record is None:
        raise InvalidRefreshTokenError(
            "유효하지 않은 Refresh Token입니다."
        )

    if record["revoked_at"] is not None:
        repository.revoke_token_family(
            session,
            record["token_family_id"],
            "refresh_token_reuse_detected",
        )
        session.commit()

        raise RefreshTokenReuseError(
            "이미 사용된 Refresh Token입니다. 다시 로그인해 주세요."
        )

    if record["expires_at"] <= now:
        repository.revoke_refresh_token(
            session,
            current_hash,
            "expired",
        )
        session.commit()

        raise InvalidRefreshTokenError(
            "Refresh Token이 만료됐습니다."
        )

    user = repository.find_user_by_id(
        session,
        record["user_id"],
    )

    if user is None or user["status"] != "active":
        repository.revoke_token_family(
            session,
            record["token_family_id"],
            "account_unavailable",
        )
        session.commit()

        raise AccountUnavailableError(
            "현재 사용할 수 없는 계정입니다."
        )

    new_refresh_token = create_refresh_token()
    new_expiry = now + timedelta(
        days=settings.refresh_token_expire_days
    )

    repository.rotate_refresh_token(
        session=session,
        old_token_id=record["id"],
        user_id=user["id"],
        token_hash=hash_token(new_refresh_token),
        token_family_id=record["token_family_id"],
        expires_at=new_expiry,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session.commit()

    return _client_tokens(
        user=user,
        refresh_token=new_refresh_token,
    )


def logout(
    session: Session,
    refresh_token: str,
) -> None:
    repository.revoke_refresh_token(
        session,
        hash_token(refresh_token),
        "logout",
    )
    session.commit()


def logout_all(
    session: Session,
    user_id: int,
) -> int:
    count = repository.revoke_all_user_tokens(
        session,
        user_id,
        "logout_all",
    )
    session.commit()
    return count


AuthService.refresh_login = staticmethod(refresh_login)
AuthService.logout = staticmethod(logout)
AuthService.logout_all = staticmethod(logout_all)
