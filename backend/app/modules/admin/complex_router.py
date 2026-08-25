from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin.complex_schemas import (
    AdminComplexDetailResponse,
    AdminComplexImageResponse,
    AdminComplexListResponse,
    AdminComplexMutationResponse,
    AdminApartmentTypeRequest,
    AdminApartmentTypeResponse,
    AdminComplexCreateRequest,
    AdminComplexCreateWithTypesRequest,
    AdminComplexUpdateRequest,
    AdminComplexRegistrationRequestListResponse,
    AdminNaverComplexLookupRequest,
    AdminNaverComplexLookupResponse,
)
from app.modules.admin.complex_service import (
    AdminApartmentTypeInUseError,
    AdminApartmentTypeNotFoundError,
    AdminComplexNotFoundError,
    AdminComplexDuplicateError,
    AdminComplexImageNotFoundError,
    AdminComplexService,
)
from app.modules.admin.naver_complex_client import (
    NaverComplexClient,
    NaverComplexLookupError,
)
from app.modules.notifications.service import NotificationService


router = APIRouter(
    prefix="/api/v1/admin/complexes",
    tags=["admin-complexes"],
)


def _lookup_naver_or_notify(
    *,
    payload: AdminNaverComplexLookupRequest,
    current_admin: dict,
    session: Session,
) -> dict:
    """신규 조회와 기존 단지 재수집의 실패 알림을 같은 흐름으로 유지한다."""
    try:
        return NaverComplexClient().lookup(**payload.model_dump())
    except NaverComplexLookupError as exc:
        NotificationService.create_unread_once(
            session,
            user_id=current_admin["id"],
            notification_type="naver_complex_collection_failed",
            title="네이버 단지정보 확인 실패",
            message=(
                f"{payload.name} 단지 기본정보를 확인하지 못했습니다. "
                "잠시 후 다시 시도하거나 서버 연동 상태를 확인해 주세요."
            ),
            target_type="naver_complex_collection",
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=AdminComplexListResponse,
)
def list_complexes(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
    q: str | None = Query(default=None),
    sido: str | None = Query(default=None),
    sigungu: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return AdminComplexService.list_complexes(
        session,
        q=q,
        sido=sido,
        sigungu=sigungu,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/registration-requests",
    response_model=AdminComplexRegistrationRequestListResponse,
)
def list_registration_requests(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
    request_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return AdminComplexService.list_registration_requests(
        session,
        status=request_status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/naver-lookup",
    response_model=AdminNaverComplexLookupResponse,
)
def lookup_naver_complex(
    payload: AdminNaverComplexLookupRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return _lookup_naver_or_notify(
        payload=payload, current_admin=current_admin, session=session
    )


@router.post(
    "/registration-requests/{request_id}/complete",
    response_model=AdminComplexMutationResponse,
)
def complete_registration_request(
    request_id: int,
    complex_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.complete_registration_request(
            session,
            request_id=request_id,
            complex_id=complex_id,
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{complex_id}",
    response_model=AdminComplexDetailResponse,
)
def get_complex(
    complex_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.get_complex(
            session,
            complex_id=complex_id,
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.post(
    "",
    response_model=AdminComplexMutationResponse,
)
def create_complex(
    payload: AdminComplexCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.create_complex(
            session,
            admin_user_id=current_admin["id"],
            values=payload.model_dump(),
        )
    except AdminComplexDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/with-types",
    response_model=AdminComplexMutationResponse,
)
def create_complex_with_types(
    payload: AdminComplexCreateWithTypesRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    data = payload.model_dump()
    apartment_types = data.pop("apartment_types")

    try:
        return AdminComplexService.create_complex_with_types(
            session,
            admin_user_id=current_admin["id"],
            values=data,
            apartment_types=apartment_types,
        )
    except AdminComplexDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.put(
    "/{complex_id}",
    response_model=AdminComplexMutationResponse,
)
def update_complex(
    complex_id: int,
    payload: AdminComplexUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.update_complex(
            session,
            complex_id=complex_id,
            admin_user_id=current_admin["id"],
            values=payload.model_dump(),
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AdminComplexDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{complex_id}/naver-refresh",
    response_model=AdminComplexDetailResponse,
)
def refresh_complex_from_naver(
    complex_id: int,
    payload: AdminNaverComplexLookupRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    naver_data = _lookup_naver_or_notify(
        payload=payload, current_admin=current_admin, session=session
    )
    try:
        return AdminComplexService.refresh_from_naver(
            session, complex_id=complex_id, naver_data=naver_data
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AdminApartmentTypeInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{complex_id}/images",
    response_model=AdminComplexImageResponse,
)
async def upload_complex_image(
    complex_id: int,
    current_admin: CurrentAdmin,
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await AdminComplexService.upload_complex_image(
            session, complex_id=complex_id, upload=upload
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put(
    "/{complex_id}/images/{image_id}/representative",
    response_model=AdminComplexImageResponse,
)
def set_representative_complex_image(
    complex_id: int,
    image_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.set_representative_image(
            session, complex_id=complex_id, image_id=image_id
        )
    except AdminComplexImageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{complex_id}/images/{image_id}",
    response_model=AdminComplexMutationResponse,
)
def delete_complex_image(
    complex_id: int,
    image_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.delete_complex_image(
            session, complex_id=complex_id, image_id=image_id
        )
    except AdminComplexImageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{complex_id}/types",
    response_model=list[AdminApartmentTypeResponse],
)
def list_apartment_types(
    complex_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        complex_data = AdminComplexService.get_complex(
            session,
            complex_id=complex_id,
        )
        return complex_data["apartment_types"]
    except AdminComplexNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.post(
    "/{complex_id}/types",
    response_model=AdminComplexMutationResponse,
)
def create_apartment_type(
    complex_id: int,
    payload: AdminApartmentTypeRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.create_apartment_type(
            session,
            complex_id=complex_id,
            values=payload.model_dump(),
        )
    except AdminComplexNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put(
    "/{complex_id}/types/{type_id}",
    response_model=AdminComplexMutationResponse,
)
def update_apartment_type(
    complex_id: int,
    type_id: int,
    payload: AdminApartmentTypeRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.update_apartment_type(
            session,
            complex_id=complex_id,
            type_id=type_id,
            values=payload.model_dump(),
        )
    except AdminApartmentTypeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{complex_id}/types/{type_id}/floor-plan",
)
async def upload_apartment_type_floor_plan(
    complex_id: int,
    type_id: int,
    current_admin: CurrentAdmin,
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await AdminComplexService.upload_apartment_type_floor_plan(
            session,
            complex_id=complex_id,
            type_id=type_id,
            upload=upload,
        )
    except AdminApartmentTypeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{complex_id}/types/{type_id}",
    response_model=AdminComplexMutationResponse,
)
def delete_apartment_type(
    complex_id: int,
    type_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminComplexService.delete_apartment_type(
            session,
            complex_id=complex_id,
            type_id=type_id,
        )
    except AdminApartmentTypeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AdminApartmentTypeInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
