from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin import server_status_service as service
from app.modules.admin.server_status_schemas import (
    ServerCleanupRequest,
    ServerCleanupResponse,
    ServerStatusResponse,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-server-status"])


@router.get("/server-status", response_model=ServerStatusResponse)
def get_server_status(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return service.get_status(session)


@router.post("/server-status/cleanup", response_model=ServerCleanupResponse)
def cleanup_server_status(
    payload: ServerCleanupRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    if current_admin.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="최고관리자만 서버 정리를 실행할 수 있습니다.",
        )
    try:
        return service.cleanup(
            session,
            targets=payload.targets,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
            password=payload.password,
        )
    except service.WrongPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
