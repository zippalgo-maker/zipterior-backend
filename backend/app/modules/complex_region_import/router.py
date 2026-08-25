from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.complex_region_import.schemas import (
    ComplexRegionImportCreateRequest,
    ComplexRegionImportJobResponse,
    SigunguOptionResponse,
)
from app.modules.complex_region_import.service import (
    ComplexRegionImportNotFoundError,
    ComplexRegionImportService,
    ComplexRegionImportStateError,
)


router = APIRouter(prefix="/api/v1/admin/complex-region-imports", tags=["admin-complex-region-import"])


def _raise_error(exc: ValueError) -> None:
    if isinstance(exc, ComplexRegionImportNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("", response_model=ComplexRegionImportJobResponse, status_code=status.HTTP_201_CREATED)
def create_complex_region_import(
    payload: ComplexRegionImportCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return ComplexRegionImportService.create_job(
        session, admin_user_id=current_admin["id"], sigungu_query=payload.sigungu_query
    )


@router.post(
    "/cross-check",
    response_model=ComplexRegionImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_complex_region_cross_check(
    payload: ComplexRegionImportCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return ComplexRegionImportService.create_cross_check_job(
        session, admin_user_id=current_admin["id"], sigungu_query=payload.sigungu_query
    )


@router.get("/sigungu-options", response_model=list[SigunguOptionResponse])
def list_sigungu_options(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> list[dict]:
    return ComplexRegionImportService.list_sigungu_options(session)


@router.get("", response_model=list[ComplexRegionImportJobResponse])
def list_complex_region_imports(
    current_admin: CurrentAdmin,
    limit: int = Query(default=30, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[dict]:
    return ComplexRegionImportService.list_jobs(session, limit=limit)


@router.get("/{job_id}", response_model=ComplexRegionImportJobResponse)
def get_complex_region_import(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return ComplexRegionImportService.get_job(session, job_id=job_id)
    except ComplexRegionImportNotFoundError as exc:
        _raise_error(exc)


@router.post(
    "/{job_id}/retry-failed-dongs",
    response_model=ComplexRegionImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def retry_complex_region_import_failed_dongs(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return ComplexRegionImportService.retry_failed_dongs(
            session, admin_user_id=current_admin["id"], job_id=job_id
        )
    except (ComplexRegionImportNotFoundError, ComplexRegionImportStateError) as exc:
        _raise_error(exc)


@router.post("/{job_id}/cancel", response_model=ComplexRegionImportJobResponse)
def cancel_complex_region_import(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return ComplexRegionImportService.cancel_job(session, job_id=job_id)
    except (ComplexRegionImportNotFoundError, ComplexRegionImportStateError) as exc:
        _raise_error(exc)
