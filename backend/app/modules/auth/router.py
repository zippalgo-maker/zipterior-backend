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
    TokenResponse,
    UserResponse,
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
