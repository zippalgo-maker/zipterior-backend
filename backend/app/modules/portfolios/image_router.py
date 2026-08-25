from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.image_service import (
    CompanyPortfolioImageService,
    PortfolioImageLimitError,
    PortfolioImageNotFoundError,
    PortfolioImageValidationError,
)
from app.modules.portfolios.schemas import (
    PortfolioImageDeleteResponse,
    PortfolioImageResponse,
    PortfolioImageSpaceMoveRequest,
    PortfolioImageUpdateRequest,
    PortfolioRepresentativeImageResponse,
)
from app.modules.portfolios.service import (
    EmptyPortfolioUpdateError,
    PortfolioAccessDeniedError,
    PortfolioNotFoundError,
    PortfolioStateConflictError,
    PortfolioValidationError,
)


router = APIRouter(
    prefix="/api/v1/company/portfolios",
    tags=["company-portfolio-images"],
)


def handle_portfolio_image_error(
    exc: ValueError,
) -> None:
    if isinstance(
        exc,
        (
            PortfolioNotFoundError,
            PortfolioImageNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PortfolioAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if isinstance(
        exc,
        (
            PortfolioStateConflictError,
            PortfolioImageLimitError,
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


@router.get(
    "/{portfolio_id}/images",
    response_model=list[PortfolioImageResponse],
)
def list_portfolio_images(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        return CompanyPortfolioImageService.list_images(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
    ) as exc:
        handle_portfolio_image_error(exc)


@router.post(
    "/{portfolio_id}/images",
    response_model=PortfolioImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_portfolio_image(
    portfolio_id: int,
    current_user: CurrentUser,
    room_code: str = Form("etc"),
    portfolio_space_id: int | None = Form(default=None),
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await CompanyPortfolioImageService.upload_image(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            room_code=room_code,
            portfolio_space_id=portfolio_space_id,
            upload=upload,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageValidationError,
        PortfolioImageLimitError,
    ) as exc:
        handle_portfolio_image_error(exc)


@router.patch(
    "/{portfolio_id}/images/{image_id}",
    response_model=PortfolioImageResponse,
)
def update_portfolio_image(
    portfolio_id: int,
    image_id: int,
    payload: PortfolioImageUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioImageService.update_image(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            image_id=image_id,
            payload=payload,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
        PortfolioImageValidationError,
        EmptyPortfolioUpdateError,
        PortfolioValidationError,
    ) as exc:
        handle_portfolio_image_error(exc)


@router.post(
    "/{portfolio_id}/images/{image_id}/space",
    response_model=PortfolioImageResponse,
)
def move_portfolio_image_to_space(
    portfolio_id: int,
    image_id: int,
    payload: PortfolioImageSpaceMoveRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioImageService.move_image_to_space(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            image_id=image_id,
            portfolio_space_id=payload.portfolio_space_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
        PortfolioImageValidationError,
        PortfolioValidationError,
    ) as exc:
        handle_portfolio_image_error(exc)


@router.post(
    "/{portfolio_id}/images/{image_id}/representative",
    response_model=PortfolioRepresentativeImageResponse,
)
def set_portfolio_representative_image(
    portfolio_id: int,
    image_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioImageService.set_representative(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
    ) as exc:
        handle_portfolio_image_error(exc)


@router.delete(
    "/{portfolio_id}/images/{image_id}",
    response_model=PortfolioImageDeleteResponse,
)
def delete_portfolio_image(
    portfolio_id: int,
    image_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioImageService.delete_image(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
    ) as exc:
        handle_portfolio_image_error(exc)
