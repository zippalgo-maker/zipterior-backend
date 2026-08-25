from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.bulk_import.schemas import (
    BulkImportJobResponse,
    BulkImportRecordListResponse,
    BulkImportRecordResponse,
    BulkUploadCreateRequest,
    ComplexResolutionRequest,
    ConfidenceThresholdRequest,
    RecordSelectionRequest,
)
from app.modules.bulk_import.service import (
    BulkImportNotFoundError,
    BulkImportService,
    BulkImportStateError,
    BulkImportValidationError,
)


router = APIRouter(
    prefix="/api/v1/admin/bulk-imports",
    tags=["admin-bulk-imports"],
)


def _raise_bulk_error(exc: ValueError) -> None:
    if isinstance(exc, BulkImportNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, BulkImportStateError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("", response_model=BulkImportJobResponse, status_code=status.HTTP_201_CREATED)
def create_bulk_upload(
    payload: BulkUploadCreateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.create_upload(
            session, admin_user_id=current_admin["id"], payload=payload
        )
    except BulkImportValidationError as exc:
        _raise_bulk_error(exc)


@router.put("/{job_id}/chunk", response_model=BulkImportJobResponse)
async def append_bulk_upload_chunk(
    job_id: int,
    current_admin: CurrentAdmin,
    offset: int = Query(ge=0),
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await BulkImportService.append_chunk(
            session,
            admin_user_id=current_admin["id"],
            job_id=job_id,
            offset=offset,
            upload=upload,
        )
    except (BulkImportNotFoundError, BulkImportStateError, BulkImportValidationError) as exc:
        _raise_bulk_error(exc)


@router.post("/{job_id}/complete-upload", response_model=BulkImportJobResponse)
def complete_bulk_upload(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.complete_upload(
            session, admin_user_id=current_admin["id"], job_id=job_id
        )
    except (BulkImportNotFoundError, BulkImportStateError, BulkImportValidationError) as exc:
        _raise_bulk_error(exc)


@router.post("/{job_id}/resolve-complexes", response_model=BulkImportJobResponse)
def resolve_bulk_complexes(
    job_id: int,
    payload: ComplexResolutionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.resolve_complexes(
            session,
            admin_user_id=current_admin["id"],
            job_id=job_id,
            payload=payload,
        )
    except (BulkImportNotFoundError, BulkImportStateError, BulkImportValidationError) as exc:
        _raise_bulk_error(exc)


@router.post("/{job_id}/start", response_model=BulkImportJobResponse)
def start_bulk_import(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.start_job(
            session, admin_user_id=current_admin["id"], job_id=job_id
        )
    except (BulkImportNotFoundError, BulkImportStateError) as exc:
        _raise_bulk_error(exc)


@router.post("/{job_id}/cancel", response_model=BulkImportJobResponse)
def cancel_bulk_import(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.cancel_job(
            session, admin_user_id=current_admin["id"], job_id=job_id
        )
    except (BulkImportNotFoundError, BulkImportStateError) as exc:
        _raise_bulk_error(exc)


@router.get("", response_model=list[BulkImportJobResponse])
def list_bulk_imports(
    current_admin: CurrentAdmin,
    limit: int = Query(default=30, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[dict]:
    return BulkImportService.list_jobs(
        session, admin_user_id=current_admin["id"], limit=limit
    )


@router.get("/{job_id}", response_model=BulkImportJobResponse)
def get_bulk_import(
    job_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.get_job(
            session, admin_user_id=current_admin["id"], job_id=job_id
        )
    except BulkImportNotFoundError as exc:
        _raise_bulk_error(exc)


@router.patch("/{job_id}/records/{record_id}/selection", response_model=BulkImportRecordResponse)
def set_bulk_import_record_selection(
    job_id: int,
    record_id: int,
    payload: RecordSelectionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.set_record_selection(
            session,
            admin_user_id=current_admin["id"],
            job_id=job_id,
            record_id=record_id,
            selected=payload.selected,
        )
    except (BulkImportNotFoundError, BulkImportStateError, BulkImportValidationError) as exc:
        _raise_bulk_error(exc)


@router.post("/{job_id}/confidence-threshold", response_model=BulkImportJobResponse)
def apply_bulk_import_confidence_threshold(
    job_id: int,
    payload: ConfidenceThresholdRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return BulkImportService.apply_confidence_threshold(
            session,
            admin_user_id=current_admin["id"],
            job_id=job_id,
            threshold=payload.threshold,
        )
    except (BulkImportNotFoundError, BulkImportStateError) as exc:
        _raise_bulk_error(exc)


@router.get("/{job_id}/records", response_model=BulkImportRecordListResponse)
def list_bulk_import_records(
    job_id: int,
    current_admin: CurrentAdmin,
    record_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    try:
        items, total = BulkImportService.list_records(
            session,
            admin_user_id=current_admin["id"],
            job_id=job_id,
            status=record_status,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except BulkImportNotFoundError as exc:
        _raise_bulk_error(exc)
