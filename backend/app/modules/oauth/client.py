"""v2.5.57(2026-08-24): SNS(카카오/네이버/Google) 로그인의 실제 외부
API 왕복(인가 URL 조립, 코드 → 토큰 교환, 프로필 조회)을 한 곳에
모은다. 이 프로젝트의 기존 외부 API 클라이언트들(예:
app/modules/admin/kakao_complex_client.py)과 동일하게 httpx/requests
같은 새 의존성을 추가하지 않고 표준 라이브러리 urllib만 쓴다.

각 제공사 개발자 콘솔에 등록해야 하는 콜백(redirect_uri)은
"{public_base_url}/api/v1/auth/oauth/{provider}/callback" 형태다
(예: https://zipterior.kr/api/v1/auth/oauth/kakao/callback).
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 8
_USER_AGENT = "Zipterior/1.0 (+https://zipterior.kr)"


class OAuthProviderError(RuntimeError):
    """외부 제공사 API 호출 실패(코드 교환/프로필 조회 등)."""


class OAuthNotConfiguredError(RuntimeError):
    """이 제공사의 Client ID/Secret이 아직 .env에 설정되지 않음."""


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_user_id: str
    email: str | None
    name: str | None


def _redirect_uri(provider: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def _post_form(url: str, params: dict[str, str], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("OAuth 토큰 교환 실패(HTTP %s): url=%s body=%s", exc.code, url, body[:500])
        raise OAuthProviderError(f"토큰 교환 실패({exc.code})") from exc
    except urllib.error.URLError as exc:
        logger.warning("OAuth 토큰 교환 실패(네트워크): url=%s reason=%s", url, exc.reason)
        raise OAuthProviderError("토큰 교환 중 네트워크 오류") from exc


def _get_json(url: str, *, bearer_token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    full_url = url if not params else f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        full_url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("OAuth 프로필 조회 실패(HTTP %s): url=%s body=%s", exc.code, url, body[:500])
        raise OAuthProviderError(f"프로필 조회 실패({exc.code})") from exc
    except urllib.error.URLError as exc:
        logger.warning("OAuth 프로필 조회 실패(네트워크): url=%s reason=%s", url, exc.reason)
        raise OAuthProviderError("프로필 조회 중 네트워크 오류") from exc


# ------------------------------- 카카오 -------------------------------

def kakao_is_configured() -> bool:
    return bool(settings.kakao_oauth_client_id)


def kakao_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.kakao_oauth_client_id or "",
        "redirect_uri": _redirect_uri("kakao"),
        "response_type": "code",
        "state": state,
    }
    return f"https://kauth.kakao.com/oauth/authorize?{urllib.parse.urlencode(params)}"


def kakao_exchange(code: str) -> OAuthProfile:
    if not kakao_is_configured():
        raise OAuthNotConfiguredError("카카오")
    params = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_oauth_client_id or "",
        "redirect_uri": _redirect_uri("kakao"),
        "code": code,
    }
    # v2.5.57: 카카오 콘솔에서 "Client Secret 사용"을 켜지 않았다면 이
    # 값이 없어도 정상 동작한다(선택 항목) -- 있으면 같이 보낸다.
    if settings.kakao_oauth_client_secret:
        params["client_secret"] = settings.kakao_oauth_client_secret
    token_data = _post_form("https://kauth.kakao.com/oauth/token", params)
    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthProviderError("카카오 access_token을 받지 못했습니다.")

    profile = _get_json("https://kapi.kakao.com/v2/user/me", bearer_token=access_token)
    kakao_account = profile.get("kakao_account") or {}
    email = kakao_account.get("email")
    nickname = (kakao_account.get("profile") or {}).get("nickname")

    return OAuthProfile(
        provider="kakao",
        provider_user_id=str(profile.get("id")),
        email=email,
        name=nickname,
    )


# ------------------------------- 네이버 -------------------------------

def naver_is_configured() -> bool:
    return bool(settings.naver_oauth_client_id)


def naver_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.naver_oauth_client_id or "",
        "redirect_uri": _redirect_uri("naver"),
        "state": state,
    }
    return f"https://nid.naver.com/oauth2.0/authorize?{urllib.parse.urlencode(params)}"


def naver_exchange(code: str, state: str) -> OAuthProfile:
    if not naver_is_configured():
        raise OAuthNotConfiguredError("네이버")
    params = {
        "grant_type": "authorization_code",
        "client_id": settings.naver_oauth_client_id or "",
        "client_secret": settings.naver_oauth_client_secret or "",
        "code": code,
        "state": state,
    }
    token_data = _post_form("https://nid.naver.com/oauth2.0/token", params)
    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthProviderError("네이버 access_token을 받지 못했습니다.")

    profile = _get_json("https://openapi.naver.com/v1/nid/me", bearer_token=access_token)
    response = profile.get("response") or {}

    return OAuthProfile(
        provider="naver",
        provider_user_id=str(response.get("id")),
        email=response.get("email"),
        name=response.get("name") or response.get("nickname"),
    )


# ------------------------------- Google -------------------------------

def google_is_configured() -> bool:
    return bool(settings.google_oauth_client_id)


def google_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_oauth_client_id or "",
        "redirect_uri": _redirect_uri("google"),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def google_exchange(code: str) -> OAuthProfile:
    if not google_is_configured():
        raise OAuthNotConfiguredError("Google")
    params = {
        "grant_type": "authorization_code",
        "client_id": settings.google_oauth_client_id or "",
        "client_secret": settings.google_oauth_client_secret or "",
        "redirect_uri": _redirect_uri("google"),
        "code": code,
    }
    token_data = _post_form("https://oauth2.googleapis.com/token", params)
    access_token = token_data.get("access_token")
    if not access_token:
        raise OAuthProviderError("Google access_token을 받지 못했습니다.")

    profile = _get_json("https://www.googleapis.com/oauth2/v3/userinfo", bearer_token=access_token)

    return OAuthProfile(
        provider="google",
        provider_user_id=str(profile.get("sub")),
        email=profile.get("email"),
        name=profile.get("name"),
    )


PROVIDERS = {
    "kakao": {
        "is_configured": kakao_is_configured,
        "authorize_url": kakao_authorize_url,
        "exchange": lambda code, state: kakao_exchange(code),
        "label": "카카오",
    },
    "naver": {
        "is_configured": naver_is_configured,
        "authorize_url": naver_authorize_url,
        "exchange": lambda code, state: naver_exchange(code, state),
        "label": "네이버",
    },
    "google": {
        "is_configured": google_is_configured,
        "authorize_url": google_authorize_url,
        "exchange": lambda code, state: google_exchange(code),
        "label": "Google",
    },
}
