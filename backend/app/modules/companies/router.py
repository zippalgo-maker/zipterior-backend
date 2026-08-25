from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.companies.schemas import (
    CompanyRegisterRequest,
    CompanyRegisterResponse,
)
from app.modules.companies.service import (
    CompanyBusinessNumberExistsError,
    CompanyEmailAlreadyExistsError,
    CompanyMembershipPlanError,
    CompanyRegistrationService,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


@router.post(
    "/register/company",
    response_model=CompanyRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_company(
    payload: CompanyRegisterRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyRegistrationService.register(
            session=session,
            payload=payload,
        )
    except CompanyEmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except CompanyBusinessNumberExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except CompanyMembershipPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


from app.common.dependencies import CurrentUser
from app.modules.companies.schemas import (
    CompanyMeResponse,
    CompanyUpdateRequest,
)
from app.modules.companies.service import (
    CompanyAccessDeniedError,
    CompanyMyPageService,
    CompanyNotFoundError,
    EmptyCompanyUpdateError,
    InvalidCompanyUpdateError,
)


company_router = APIRouter(
    prefix="/api/v1/company",
    tags=["company"],
)


def handle_company_mypage_error(
    exc: ValueError,
) -> None:
    if isinstance(exc, CompanyNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, CompanyAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    ) from exc


@company_router.get(
    "/me",
    response_model=CompanyMeResponse,
)
def get_my_company(
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyMyPageService.get_me(
            session=session,
            user=current_user,
        )
    except (
        CompanyAccessDeniedError,
        CompanyNotFoundError,
    ) as exc:
        handle_company_mypage_error(exc)


@company_router.patch(
    "/me",
    response_model=CompanyMeResponse,
)
def update_my_company(
    payload: CompanyUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyMyPageService.update_me(
            session=session,
            user=current_user,
            payload=payload,
        )
    except (
        CompanyAccessDeniedError,
        CompanyNotFoundError,
        EmptyCompanyUpdateError,
        InvalidCompanyUpdateError,
    ) as exc:
        handle_company_mypage_error(exc)


from app.modules.companies.schemas import (
    CompanyServiceRegionCreateRequest,
    CompanyServiceRegionDeleteResponse,
    CompanyServiceRegionResponse,
)
from app.modules.companies.service import (
    CompanyServiceRegionService,
    ServiceRegionAlreadyExistsError,
    ServiceRegionLimitError,
    ServiceRegionNotFoundError,
)


def handle_service_region_error(
    exc: ValueError,
) -> None:
    if isinstance(exc, ServiceRegionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, CompanyAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            ServiceRegionAlreadyExistsError,
            ServiceRegionLimitError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    ) from exc


@company_router.get(
    "/service-regions",
    response_model=list[CompanyServiceRegionResponse],
)
def get_company_service_regions(
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        return CompanyServiceRegionService.list_regions(
            session=session,
            user=current_user,
        )
    except (
        CompanyAccessDeniedError,
        CompanyNotFoundError,
    ) as exc:
        handle_service_region_error(exc)


@company_router.post(
    "/service-regions",
    response_model=CompanyServiceRegionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company_service_region(
    payload: CompanyServiceRegionCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyServiceRegionService.create_region(
            session=session,
            user=current_user,
            payload=payload,
        )
    except (
        CompanyAccessDeniedError,
        CompanyNotFoundError,
        ServiceRegionAlreadyExistsError,
        ServiceRegionLimitError,
    ) as exc:
        handle_service_region_error(exc)


@company_router.delete(
    "/service-regions/{region_id}",
    response_model=CompanyServiceRegionDeleteResponse,
)
def delete_company_service_region(
    region_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyServiceRegionService.delete_region(
            session=session,
            user=current_user,
            region_id=region_id,
        )
    except (
        CompanyAccessDeniedError,
        CompanyNotFoundError,
        ServiceRegionNotFoundError,
    ) as exc:
        handle_service_region_error(exc)
