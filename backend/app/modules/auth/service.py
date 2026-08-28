import secrets
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
from app.modules.audit.service import AuditService
from app.modules.auth import repository
from app.modules.auth.schemas import CustomerRegisterRequest, LoginRequest
from app.modules.auth.sso_bridge import verify_code_with_zippalgo360


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
            # 2026-08-26: 업체 자체가입(company.self_registered)은 이미
            # 감사로그에 남는데 일반회원 가입은 안 남고 있었다 -- 관리자
            # 대시보드 "신규 가입 회원" 위젯의 데이터 소스로 씀.
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="user.self_registered",
                target_type="user",
                target_id=user["id"],
                after_data={"user_id": user["id"], "role": "customer", "user_status": user["status"]},
                reason="일반회원 직접 가입",
                metadata={"source": "public_api"},
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


def sso_exchange(
    session: Session,
    code: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any] | None:
    """집팔고360 SSO 1회용 코드를 검증하고, 이메일 기준으로 기존 계정을
    찾거나(customer role만) 새로 만들어 로그인시킨다.
    설계: zippalgo360 저장소 docs/WORK_LOG.md "로그인 통합 설계 제안" 섹션.
    실패하면(설정 안 됨/코드 무효/역할 미지원/계정 비활성) 예외를 던지지
    않고 None을 반환 — 호출부(router)가 400으로 응답하면 프론트는 조용히
    기존 로그인 화면으로 폴백한다(집테리어 자체 로그인엔 영향 없음).
    """
    if not settings.sso_shared_secret:
        return None

    identity = verify_code_with_zippalgo360(code)
    if identity is None:
        return None

    # v1 범위: 집팔고360 customer 역할만 자동 연동한다. company(업체) 계정
    # 연동은 사업자등록번호 등 온보딩 정책이 따로 필요해서 범위 밖으로
    # 남겨둠 — company 역할이면 그냥 폴백시킨다.
    if identity.get("role") != "customer":
        return None

    email = str(identity.get("email") or "").strip().lower()
    if not email:
        return None

    user = repository.find_user_by_email(session, email)

    if user is None:
        random_password = secrets.token_urlsafe(32)
        try:
            user = repository.create_customer(
                session=session,
                email=email,
                password_hash=hash_password(random_password),
                name=identity.get("name") or email,
                nickname=None,
                phone=None,
                marketing_agreed=False,
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            user = repository.find_user_by_email(session, email)
            if user is None:
                return None

    if user["status"] != "active":
        return None

    access_token = create_access_token(user_id=user["id"], role=user["role"])
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

    repository.update_last_login(session, user["id"])
    repository.record_login_attempt(
        session=session,
        user_id=user["id"],
        email=email,
        was_successful=True,
        failure_reason=None,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"source": "zippalgo360_sso"},
    )

    session.commit()

    refreshed_user = repository.find_user_by_id(session, user["id"])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": refreshed_user,
    }


AuthService.sso_exchange = staticmethod(sso_exchange)
