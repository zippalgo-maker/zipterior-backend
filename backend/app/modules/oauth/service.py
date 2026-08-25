"""v2.5.57(2026-08-24): SNS 로그인 오케스트레이션.
1) /authorize: state(CSRF 방지용, 우리 서버가 서명한 단명 JWT)를 만들어
   제공사 인가 화면으로 리다이렉트.
2) /callback: state 검증 → code를 프로필로 교환 → 이미 연결된 계정이면
   로그인, 이메일이 같은 기존 customer 계정이 있으면 그 계정에 연결,
   둘 다 아니면 새 customer 계정을 만든다 → auth 모듈과 동일한 방식
   으로 우리 access/refresh token을 발급(로그인 시도 기록까지 동일).
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_token
from app.modules.auth import repository as auth_repository
from app.modules.oauth import client
from app.modules.oauth import repository as oauth_repository


STATE_TTL_MINUTES = 10


class OAuthStateError(ValueError):
    pass


class OAuthAccountRoleError(ValueError):
    """SNS 계정이 고객이 아닌 역할(업체/관리자)에 이미 연결돼 있음."""


class OAuthAlreadyLinkedToOtherUserError(ValueError):
    """F13(2026-08-25): 로그인 상태에서 SNS 계정을 지금 계정에 연결하려
    했는데, 그 SNS 계정이 이미 다른 사용자 계정에 연결돼 있음."""


def _state_secret() -> str:
    return settings.oauth_state_secret or settings.jwt_secret_key


def build_state(*, provider: str, next_path: str, link_user_id: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "provider": provider,
        "next": next_path,
        "nonce": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=STATE_TTL_MINUTES),
    }
    # F13(2026-08-25): 로그인 상태에서 "SNS 계정 연결"을 시작할 때만
    # 채워짐 -- 브라우저 전체 리다이렉트라 헤더로 신원을 못 넘기니
    # (WebSocket 토큰-쿼리스트링과 같은 이유) 서명된 state 안에 실어
    # 보낸다. 콜백에서 이 값이 있으면 로그인이 아니라 "연결"로 처리.
    if link_user_id is not None:
        payload["link_user_id"] = link_user_id
    return jwt.encode(payload, _state_secret(), algorithm=settings.jwt_algorithm)


def peek_next(state: str | None) -> str | None:
    """서명 검증 없이 state JWT의 next만 훔쳐본다 -- 순수 라우팅
    용도(에러 발생 시 '어디로 돌려보낼지'만 결정)라 위조돼도 실제
    로그인/권한에는 영향 없음(로그인 자체는 verify_state를 반드시
    거치는 handle_callback에서만 이뤄짐). state가 아예 없거나 형식이
    깨졌으면 조용히 None."""
    if not state:
        return None
    try:
        payload = jwt.decode(state, options={"verify_signature": False})
        next_path = payload.get("next")
        return next_path if isinstance(next_path, str) else None
    except Exception:
        return None


def peek_is_link(state: str | None) -> bool:
    """peek_next와 동일한 이유로 서명 검증 없이 훔쳐본다 -- 에러 발생
    시 로그인 실패 착지(/login, /m)로 보낼지 SNS 연결 실패 착지
    (oauth-callback.html#linked=0)로 보낼지 "라우팅만" 결정하는 용도.
    실제 연결 여부는 handle_link_callback 안에서 verify_state로 서명을
    검증한 뒤에만 확정된다."""
    if not state:
        return False
    try:
        payload = jwt.decode(state, options={"verify_signature": False})
        return bool(payload.get("link_user_id"))
    except Exception:
        return False


def verify_state(state: str, *, expected_provider: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(state, _state_secret(), algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:
        raise OAuthStateError("만료되었거나 위조된 요청입니다. 다시 시도해 주세요.") from exc
    if payload.get("provider") != expected_provider:
        raise OAuthStateError("잘못된 인증 요청입니다.")
    return payload


def is_configured(provider: str) -> bool:
    entry = client.PROVIDERS.get(provider)
    return bool(entry and entry["is_configured"]())


def authorize_url(provider: str, *, next_path: str) -> str:
    entry = client.PROVIDERS.get(provider)
    if entry is None:
        raise ValueError(f"알 수 없는 SNS 제공사: {provider}")
    state = build_state(provider=provider, next_path=next_path)
    return entry["authorize_url"](state)


def handle_callback(
    session: Session,
    *,
    provider: str,
    code: str,
    state: str,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """성공 시 {"next": str, "access_token":..., "refresh_token":...,
    "expires_in":...}를 돌려준다(라우터가 이걸로 프론트 콜백 페이지로
    리다이렉트한다)."""
    entry = client.PROVIDERS.get(provider)
    if entry is None:
        raise ValueError(f"알 수 없는 SNS 제공사: {provider}")

    payload = verify_state(state, expected_provider=provider)
    next_path = payload.get("next") or "/my"

    profile = entry["exchange"](code, state)

    linked = oauth_repository.find_oauth_account(
        session,
        provider=provider,
        provider_user_id=profile.provider_user_id,
    )

    if linked:
        user = auth_repository.find_user_by_id(session, linked["user_id"])
        if user is None:
            # 연결은 있는데 계정이 삭제된 예외 상황 -- 새로 만들지 않고
            # 명확히 실패시킨다(고아 계정을 조용히 되살리지 않음).
            raise OAuthAccountRoleError("연결된 계정을 찾을 수 없습니다. 이메일로 다시 가입해 주세요.")
    else:
        existing = auth_repository.find_user_by_email(session, profile.email) if profile.email else None
        if existing:
            user = existing
        else:
            # v2.5.58(2026-08-24): 카카오 "카카오계정(이메일)" 동의항목은
            # 콘솔에서 "권한 없음"으로 표시되는 별도 심사 대상 항목이라
            # (추가 기능 신청 → 비즈니스 채널 연결·사업자/개인 인증·
            # 개인정보처리방침 등록이 선행돼야 하고 며칠 걸릴 수 있음),
            # 심사를 기다리지 않고 지금 바로 로그인이 되도록 이메일이
            # 없으면 제공사+제공사쪽 유저ID로 만든 식별 가능한 가짜
            # 이메일(실제 배달 불가, admin 화면에서 "@no-email."로
            # 바로 알아볼 수 있게)로 계정을 만든다. 이메일 심사가
            # 나중에 승인되면 이 계정에 실제 이메일을 연결하는 기능은
            # 아직 없음(필요해지면 "이메일 등록" 같은 별도 기능으로
            # 추가해야 함 -- 지금은 로그인 자체를 막지 않는 게 우선
            # 이라는 사용자 명시적 선택, V2.5.0_PLAN.md 참고).
            email = profile.email or f"{provider}_{profile.provider_user_id}@no-email.zipterior.kr"
            user = oauth_repository.create_oauth_customer(
                session,
                email=email,
                name=profile.name or f"{entry['label']} 사용자",
            )
        oauth_repository.link_oauth_account(
            session,
            user_id=user["id"],
            provider=provider,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
        )

    if user["role"] != "customer":
        # v2.5.57: 업체/관리자 계정과 같은 이메일이 우연히 SNS에 있는
        # 경우 -- 절대 그 계정에 자동 연결하지 않고 막는다(권한 상승
        # 방지). 이 상황은 계정 연결(link_oauth_account)이 아직 안
        # 일어난 시점이므로 여기서 막아도 side effect 없음.
        raise OAuthAccountRoleError("이 이메일은 일반회원이 아닌 계정으로 등록되어 있습니다.")

    if user["status"] != "active":
        raise OAuthAccountRoleError("현재 로그인할 수 없는 계정입니다.")

    access_token = create_access_token(user_id=user["id"], role=user["role"])
    refresh_token = create_refresh_token()
    refresh_expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    auth_repository.create_refresh_token_record(
        session=session,
        user_id=user["id"],
        token_hash=hash_token(refresh_token),
        token_family_id=uuid4(),
        expires_at=refresh_expire,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    auth_repository.update_last_login(session, user["id"])
    auth_repository.record_login_attempt(
        session=session,
        user_id=user["id"],
        email=user["email"],
        was_successful=True,
        failure_reason=None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.commit()

    return {
        "next": next_path,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.access_token_expire_minutes * 60,
    }


def handle_link_callback(
    session: Session,
    *,
    provider: str,
    code: str,
    state: str,
    link_user_id: int,
) -> dict[str, Any]:
    """F13(2026-08-25): 이미 로그인된 사용자가 SNS 계정을 지금 계정에
    연결한다. handle_callback(로그인 흐름)과 완전히 분리 -- 이메일로
    다른 계정에 자동으로 붙거나 새 계정을 만드는 로직을 전혀 타지
    않는다. 오직 state에 서명된 link_user_id 계정에만, 그 SNS 계정이
    이미 다른 사람 것이 아닐 때만 연결한다."""
    entry = client.PROVIDERS.get(provider)
    if entry is None:
        raise ValueError(f"알 수 없는 SNS 제공사: {provider}")

    payload = verify_state(state, expected_provider=provider)
    if payload.get("link_user_id") != link_user_id:
        # state가 위조되지 않는 한 발생하지 않지만, 방어적으로 한 번 더 확인.
        raise OAuthStateError("잘못된 연결 요청입니다. 다시 시도해 주세요.")
    next_path = payload.get("next") or "/my#profile"

    user = auth_repository.find_user_by_id(session, link_user_id)
    if user is None or user["role"] != "customer" or user["status"] != "active":
        raise OAuthAccountRoleError("계정을 확인할 수 없습니다. 다시 로그인한 뒤 시도해 주세요.")

    profile = entry["exchange"](code, state)

    linked = oauth_repository.find_oauth_account(
        session,
        provider=provider,
        provider_user_id=profile.provider_user_id,
    )
    if linked and linked["user_id"] != link_user_id:
        raise OAuthAlreadyLinkedToOtherUserError(
            "이 SNS 계정은 이미 다른 계정에 연결되어 있습니다."
        )

    # linked가 없거나(신규 연결) 이미 이 계정에 연결돼 있으면(재연결,
    # 멱등) 둘 다 그대로 upsert -- link_oauth_account의 ON CONFLICT가
    # 이메일/updated_at만 갱신하므로 안전하다.
    oauth_repository.link_oauth_account(
        session,
        user_id=link_user_id,
        provider=provider,
        provider_user_id=profile.provider_user_id,
        email=profile.email,
    )
    session.commit()

    return {"next": next_path}
