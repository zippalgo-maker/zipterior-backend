from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenValidationError, decode_access_token
from app.modules.auth import repository


bearer_scheme = HTTPBearer(auto_error=False)

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (TokenValidationError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 유효하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = repository.find_user_by_id(
        session,
        user_id,
    )

    if user is None or user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용할 수 없는 계정입니다.",
        )

    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def get_current_admin(
    current_user: CurrentUser,
) -> dict[str, Any]:
    if current_user["role"] not in {
        "admin",
        "super_admin",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )

    return current_user


CurrentAdmin = Annotated[
    dict[str, Any],
    Depends(get_current_admin),
]


def get_optional_current_user(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict[str, Any] | None:
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (TokenValidationError, ValueError, KeyError):
        return None

    user = repository.find_user_by_id(
        session,
        user_id,
    )

    if user is None or user["status"] != "active":
        return None

    return user


OptionalCurrentUser = Annotated[
    dict[str, Any] | None,
    Depends(get_optional_current_user),
]
