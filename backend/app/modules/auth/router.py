from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.auth.schemas import (
    CustomerRegisterRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    SsoExchangeRequest,
    TokenResponse,
    UserResponse,
    UserSettingsUpdateRequest,
)
from app.modules.auth import repository
from pydantic import EmailStr

from app.modules.auth.service import (
    AccountUnavailableError,
    AuthService,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


def public_user(user: dict) -> dict:
    return {
        key: value
        for key, value in user.items()
        if key not in {
            "password_hash",
            "last_login_at",
            "updated_at",
            "deleted_at",
        }
    }


@router.post(
    "/register/customer",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_customer(
    payload: CustomerRegisterRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        user = AuthService.register_customer(
            session,
            payload,
        )
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return public_user(user)


@router.get("/check-email")
def check_email(email: EmailStr, session: Session = Depends(get_db)) -> dict:
    normalized=str(email).strip().lower()
    return {"email": normalized, "available": repository.find_user_by_email(session, normalized) is None}


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.client.host if request.client else None
    )

    try:
        result = AuthService.login(
            session,
            payload,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except AccountUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    result["user"] = public_user(result["user"])
    return result


@router.get(
    "/me",
    response_model=UserResponse,
)
def me(current_user: CurrentUser) -> dict:
    return public_user(current_user)


# v1.10.1(2026-08-26): 알림 설정 화면(목업 15번) -- 견적응답/시공업체댓글/
# 현장사진 3개 토글 + 마케팅 동의. 부분 갱신(넘긴 키만 바뀜)이라 기존
# notification_prefs와 merge해서 저장한다.
@router.patch("/me/settings", response_model=UserResponse)
def update_my_settings(
    payload: UserSettingsUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    prefs_update = None
    if payload.notification_prefs is not None:
        merged = dict(current_user.get("notification_prefs") or {})
        merged.update(payload.notification_prefs.model_dump(exclude_none=True))
        prefs_update = merged
    row = repository.update_user_settings(
        session,
        user_id=current_user["id"],
        notification_prefs=prefs_update,
        marketing_agreed=payload.marketing_agreed,
    )
    return public_user(row)


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    payload: RefreshTokenRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.client.host if request.client else None
    )

    try:
        result = AuthService.refresh_login(
            session,
            payload.refresh_token,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
        )
    except RefreshTokenReuseError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except AccountUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    result["user"] = public_user(result["user"])
    return result


@router.post(
    "/logout",
    response_model=MessageResponse,
)
def logout(
    payload: LogoutRequest,
    session: Session = Depends(get_db),
) -> dict:
    AuthService.logout(
        session,
        payload.refresh_token,
    )
    return {"message": "로그아웃되었습니다."}


@router.post(
    "/logout-all",
    response_model=MessageResponse,
)
def logout_all(
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    AuthService.logout_all(
        session,
        current_user["id"],
    )
    return {"message": "모든 기기에서 로그아웃되었습니다."}


@router.post(
    "/sso/exchange",
    response_model=TokenResponse,
)
def sso_exchange(
    payload: SsoExchangeRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """집팔고360 로그인 사용자를 iframe(/jipterior) 진입 시 자동으로
    집테리어 계정에 연동한다. 실패하면 400을 던지고, 프론트는 이걸
    조용히 무시하고 기존 로그인 화면으로 폴백한다(집테리어 자체
    로그인은 전혀 영향 없음). 설계: zippalgo360 저장소
    docs/WORK_LOG.md "로그인 통합 설계 제안" 섹션 참고.
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.client.host if request.client else None
    )

    result = AuthService.sso_exchange(
        session,
        payload.code,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO 로그인을 처리할 수 없습니다.",
        )

    result["user"] = public_user(result["user"])
    return result
