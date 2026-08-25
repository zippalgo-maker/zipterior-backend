"""v2.5.57(2026-08-24): SNS 로그인 엔드포인트.
GET /api/v1/auth/oauth/{provider}/authorize  -- 제공사 인가 화면으로 302
GET /api/v1/auth/oauth/{provider}/callback   -- 코드 처리 후 프론트로 302

토큰을 쿼리스트링이 아니라 URL 프래그먼트(#)로 넘긴다 -- 프래그먼트는
브라우저가 서버로 절대 보내지 않아서(Referer에도 안 실림) access_token/
refresh_token이 nginx 접근 로그나 리퍼러에 남지 않는다. 프론트
oauth-callback.html이 location.hash를 읽어 처리한다.
"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.config import settings
from app.core.database import get_db
from fastapi import Depends

from app.modules.oauth import client
from app.modules.oauth.client import OAuthNotConfiguredError, OAuthProviderError
from app.modules.oauth.service import (
    OAuthAccountRoleError,
    OAuthAlreadyLinkedToOtherUserError,
    OAuthStateError,
    authorize_url,
    build_state,
    handle_callback,
    handle_link_callback,
    is_configured,
    peek_is_link,
    peek_next,
)


logger = logging.getLogger(__name__)


def jwt_decode_unverified(state: str) -> dict:
    import jwt as _jwt
    return _jwt.decode(state, options={"verify_signature": False})

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])

_VALID_PROVIDERS = set(client.PROVIDERS.keys())


def _login_page_error_redirect(*, provider: str, reason: str, next_hint: str | None = None) -> RedirectResponse:
    base = settings.public_base_url.rstrip("/")
    # v2.5.57: 모바일 앱 셸(/m)에서 시작된 흐름이 실패하면 데스크톱
    # /login이 아니라 /m으로 돌려보내야 사용자가 원래 있던 화면으로
    # 돌아온다(모바일 로그인 화면 자체가 /m 안의 오버레이라 별도
    # URL이 없음). "/my"도 "/m"으로 시작하는 문자열이라 단순
    # startswith("/m")는 "/my"(데스크톱 마이페이지)까지 잘못 잡는다
    # (실제로 겪은 버그 -- 테스트 중 발견) -- "/m" 자체이거나 "/m/"로
    # 시작할 때만 모바일로 판단한다.
    landing = "/m" if next_hint and (next_hint == "/m" or next_hint.startswith("/m/")) else "/login"
    url = f"{base}{landing}?oauth_error={quote(reason)}&provider={quote(provider)}"
    return RedirectResponse(url, status_code=302)


def _link_result_redirect(
    *, provider: str, next_hint: str, linked: bool, reason: str | None = None
) -> RedirectResponse:
    # F13(2026-08-25): 로그인 상태에서 SNS "연결"을 시도한 경우 전용
    # 착지 -- 이미 로그인돼 있으므로 토큰을 새로 발급하지 않고(기존
    # 세션 그대로), 같은 oauth-callback.html을 linked=1/0 해시로만
    # 다르게 재사용한다.
    base = settings.public_base_url.rstrip("/")
    fragment = f"linked={'1' if linked else '0'}&provider={quote(provider)}"
    if reason:
        fragment += f"&reason={quote(reason)}"
    fragment += f"&next={quote(next_hint or '/my#profile')}"
    url = f"{base}/oauth-callback.html#{fragment}"
    return RedirectResponse(url, status_code=302)


@router.post("/{provider}/link-url")
def oauth_link_url(
    provider: str,
    current_user: CurrentUser,
    next: str = Query(default="/my#profile"),
) -> dict:
    # F13(2026-08-25): 로그인된 사용자가 지금 계정에 SNS를 연결하기
    # 위한 인가 URL을 발급. 브라우저가 이 URL로 전체 리다이렉트하므로
    # Authorization 헤더를 못 실어 보낸다 -- 그래서 여기서 인증된
    # fetch로 "완성된 URL"만 받고(토큰 자체는 URL에 없음), 그다음
    # location.href로 이동하는 2단계 구조.
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="지원하지 않는 로그인 방법입니다.")
    if current_user["role"] != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="일반회원 계정만 SNS 연동을 사용할 수 있습니다.")
    if not is_configured(provider):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="아직 준비 중인 로그인 방법입니다.")

    safe_next = next if next.startswith("/") and not next.startswith("//") else "/my#profile"
    # authorize_url()은 내부적으로 build_state를 새로 호출해 link_user_id가
    # 안 실린 state를 만들어버리므로, 여기서는 위에서 link_user_id를 실어
    # 만든 state로 client.PROVIDERS를 직접 써서 URL을 조립한다.
    state = build_state(provider=provider, next_path=safe_next, link_user_id=current_user["id"])
    entry = client.PROVIDERS[provider]
    url = entry["authorize_url"](state)
    return {"url": url}


@router.get("/{provider}/authorize")
def oauth_authorize(
    provider: str,
    next: str = Query(default="/my"),
) -> RedirectResponse:
    if provider not in _VALID_PROVIDERS:
        return _login_page_error_redirect(provider=provider, reason="unknown_provider", next_hint=next)

    if not is_configured(provider):
        # v2.5.57: 관리자가 아직 이 제공사 API 키를 안 넣었을 때, 서버
        # 에러(500)나 깨진 리다이렉트 대신 로그인 화면으로 안전하게
        # 돌려보내고 프론트가 "준비 중" 토스트를 띄우게 한다.
        return _login_page_error_redirect(provider=provider, reason="not_configured", next_hint=next)

    # next는 우리 자신의 상대경로만 허용(오픈 리다이렉트 방지).
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/my"
    url = authorize_url(provider, next_path=safe_next)
    return RedirectResponse(url, status_code=302)


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    next_hint = peek_next(state)
    # F13(2026-08-25): "로그인" 콜백과 "SNS 연결" 콜백이 같은 엔드포인트를
    # 공유한다(제공사가 등록해둔 콜백 URL은 하나뿐이라서). state 안의
    # link_user_id 유무로 어느 쪽인지 구분 -- is_link는 서명 검증 전
    # peek이라 "에러가 나면 어디로 돌려보낼지" 라우팅에만 쓰고, 실제
    # 연결 여부는 아래 handle_link_callback이 verify_state로 다시
    # 검증한 뒤에만 확정한다(peek_next와 동일한 안전 모델).
    is_link = peek_is_link(state)

    def err(reason: str) -> RedirectResponse:
        if is_link:
            return _link_result_redirect(provider=provider, next_hint=next_hint or "/my#profile", linked=False, reason=reason)
        return _login_page_error_redirect(provider=provider, reason=reason, next_hint=next_hint)

    if provider not in _VALID_PROVIDERS:
        return err("unknown_provider")

    if error:
        # 사용자가 제공사 동의 화면에서 취소한 경우 등.
        return err("cancelled")

    if not code or not state:
        return err("missing_code")

    forwarded = request.headers.get("x-forwarded-for")
    ip_address = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)

    if is_link:
        try:
            payload = jwt_decode_unverified(state)
            link_user_id = int(payload.get("link_user_id"))
            result = handle_link_callback(
                session,
                provider=provider,
                code=code,
                state=state,
                link_user_id=link_user_id,
            )
        except OAuthStateError as exc:
            logger.warning("OAuth(연결) state 검증 실패: provider=%s error=%s", provider, exc)
            return err("state_invalid")
        except OAuthNotConfiguredError:
            return err("not_configured")
        except OAuthAlreadyLinkedToOtherUserError as exc:
            logger.info("OAuth 연결 거부(다른 계정에 이미 연결됨): provider=%s error=%s", provider, exc)
            return err("already_linked_elsewhere")
        except OAuthAccountRoleError as exc:
            logger.info("OAuth 연결 계정 확인 실패: provider=%s error=%s", provider, exc)
            return err("role_conflict")
        except OAuthProviderError as exc:
            logger.warning("OAuth 제공사 API 실패: provider=%s error=%s", provider, exc)
            return err("provider_error")
        except (ValueError, TypeError) as exc:
            logger.info("OAuth 연결 콜백 처리 실패: provider=%s error=%s", provider, exc)
            return err("provider_error")

        return _link_result_redirect(provider=provider, next_hint=result["next"], linked=True)

    try:
        result = handle_callback(
            session,
            provider=provider,
            code=code,
            state=state,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
        )
    except OAuthStateError as exc:
        logger.warning("OAuth state 검증 실패: provider=%s error=%s", provider, exc)
        return _login_page_error_redirect(provider=provider, reason="state_invalid", next_hint=next_hint)
    except OAuthNotConfiguredError:
        return _login_page_error_redirect(provider=provider, reason="not_configured", next_hint=next_hint)
    except OAuthAccountRoleError as exc:
        logger.info("OAuth 계정 정책 위반: provider=%s error=%s", provider, exc)
        return _login_page_error_redirect(provider=provider, reason="role_conflict", next_hint=next_hint)
    except OAuthProviderError as exc:
        logger.warning("OAuth 제공사 API 실패: provider=%s error=%s", provider, exc)
        return _login_page_error_redirect(provider=provider, reason="provider_error", next_hint=next_hint)
    except ValueError as exc:
        logger.info("OAuth 콜백 처리 실패: provider=%s error=%s", provider, exc)
        return _login_page_error_redirect(provider=provider, reason="no_email", next_hint=next_hint)

    base = settings.public_base_url.rstrip("/")
    fragment = (
        f"at={quote(result['access_token'])}"
        f"&rt={quote(result['refresh_token'])}"
        f"&ei={result['expires_in']}"
        f"&next={quote(result['next'])}"
    )
    url = f"{base}/oauth-callback.html#{fragment}"
    return RedirectResponse(url, status_code=302)
