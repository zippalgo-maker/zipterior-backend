import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.modules.audit.service import AuditService
from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import repository
from app.modules.portfolios.schemas import PortfolioImageUpdateRequest
from app.modules.portfolios.service import (
    CompanyPortfolioService,
    EmptyPortfolioUpdateError,
    PortfolioAccessDeniedError,
    PortfolioNotFoundError,
    PortfolioStateConflictError,
    PortfolioValidationError,
)


PORTFOLIO_UPLOAD_ROOT = Path(
    "/var/www/zipterior/uploads/portfolios"
)
PORTFOLIO_URL_PREFIX = "/uploads/portfolios"

MAX_IMAGE_SIZE = 50 * 1024 * 1024
# v2.5.0: 대량등록에서 원본 사진을 개수 제한 없이 등록하려면 이 값도 함께
# 올려야 실제로 막히지 않는다. 완전 무제한은 위험하니 안전망으로 높은
# 값만 둔다.
# v2.5.40 (2026-08-23): 200이 실제로 걸린 사례 발견(포트폴리오 #1241,
# 원본 205장 중 200장만 저장) -- 실제 콘텐츠가 200장을 넘는 포폴이
# 존재해서 500으로 상향. 여전히 "완전 무제한은 아닌 안전망"이라는
# 원칙은 유지(위 주석 참고), 값만 올림.
MAX_IMAGES_PER_PORTFOLIO = 500

ALLOWED_ROOM_CODES = {
    "living_room",
    "kitchen",
    "master_room",
    "room",
    "bathroom",
    "entrance",
    "balcony",
    "dressing_room",
    "utility_room",
    "etc",
}

ALLOWED_MIME_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}

EDITABLE_PORTFOLIO_STATUSES = {
    "draft",
    "rejected",
    "hidden",
}


class PortfolioImageNotFoundError(ValueError):
    pass


class PortfolioImageValidationError(ValueError):
    pass


class PortfolioImageLimitError(ValueError):
    pass


def _portfolio_directory(
    portfolio_id: int,
) -> Path:
    return PORTFOLIO_UPLOAD_ROOT / str(portfolio_id)


def _original_extension(
    mime_type: str | None,
) -> str:
    if mime_type in ALLOWED_MIME_TYPES:
        return ALLOWED_MIME_TYPES[mime_type][1]

    return ".bin"


def _original_path_from_record(
    image: dict[str, Any],
) -> Path:
    extension = _original_extension(
        image.get("original_mime_type")
    )

    return (
        _portfolio_directory(image["portfolio_id"])
        / "original"
        / f"{image['stored_filename']}{extension}"
    )


def _managed_path_from_url(
    url_path: str | None,
) -> Path | None:
    if not url_path:
        return None

    expected_prefix = f"{PORTFOLIO_URL_PREFIX}/"

    if not url_path.startswith(expected_prefix):
        return None

    relative_path = url_path.removeprefix(
        expected_prefix
    )

    if ".." in relative_path:
        return None

    return PORTFOLIO_UPLOAD_ROOT / relative_path


def _remove_image_files(
    image: dict[str, Any],
) -> None:
    paths = [
        _original_path_from_record(image),
        _managed_path_from_url(image.get("large_path")),
        _managed_path_from_url(image.get("medium_path")),
        _managed_path_from_url(
            image.get("thumbnail_path")
        ),
    ]

    for path in paths:
        if path is None:
            continue

        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass

    portfolio_root = _portfolio_directory(
        image["portfolio_id"]
    )

    for subdirectory in (
        "original",
        "large",
        "medium",
        "thumbnail",
    ):
        directory = portfolio_root / subdirectory

        try:
            if directory.exists() and not any(
                directory.iterdir()
            ):
                directory.rmdir()
        except OSError:
            pass

    try:
        if portfolio_root.exists() and not any(
            portfolio_root.iterdir()
        ):
            portfolio_root.rmdir()
    except OSError:
        pass


def _prepare_directories(
    portfolio_id: int,
) -> dict[str, Path]:
    root = _portfolio_directory(portfolio_id)

    directories = {
        "large": root / "large",
        "medium": root / "medium",
        "thumbnail": root / "thumbnail",
    }

    for directory in directories.values():
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    return directories


def _save_webp_variant(
    source: Image.Image,
    *,
    target_path: Path,
    max_dimension: int,
    quality: int,
    max_size_bytes: int | None = None,
) -> tuple[int, int, int]:
    image = source.copy()
    image.thumbnail(
        (max_dimension, max_dimension),
        Image.Resampling.LANCZOS,
    )

    if image.mode not in {
        "RGB",
        "RGBA",
    }:
        image = image.convert("RGB")

    current_quality = quality

    while True:
        image.save(
            target_path,
            format="WEBP",
            quality=current_quality,
            # method=6은 libwebp의 최고 압축 노력 설정(가장 느림). 사진
            # 콘텐츠 기준 실측 결과 method=4가 인코딩 시간을 약 절반으로
            # 줄이면서 파일 용량은 10% 안팎만 늘어나 육안 품질 차이가 거의
            # 없다(2026-08-19 대량등록 속도 개선 시 확인).
            method=4,
        )

        size_bytes = target_path.stat().st_size

        if (
            max_size_bytes is None
            or size_bytes <= max_size_bytes
            or current_quality <= 68
        ):
            break

        current_quality = max(
            68,
            current_quality - 4,
        )

    width, height = image.size

    return width, height, size_bytes


class CompanyPortfolioImageService:
    @staticmethod
    def _get_editable_context(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 관리자 일괄등록은 실제 업체 회원을 임의 생성하지 않고도 기존 이미지
        # 검증·리사이즈·감사 흐름을 그대로 사용한다. 이 내부 키는 JWT 사용자에
        # 생성되지 않으며 super_admin worker만 전달한다.
        import_company_id = user.get("_bulk_import_company_id")
        if import_company_id and user.get("role") == "super_admin":
            company = {
                "id": int(import_company_id),
                "member_role": "admin_proxy",
            }
        else:
            company = CompanyPortfolioService.get_company(
                session,
                user,
            )
            CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        # 관리자 "원본대조·수정" 화면은 이미 승인·공개된 포트폴리오도
        # 편집해야 하므로, 위의 관리자 대리 컨텍스트(_bulk_import_company_id
        # + super_admin)와 별도로 이 플래그가 명시적으로 켜져 있을 때만
        # 상태 제한을 건너뛴다. 실제 업체 회원 요청이나 일괄등록 워커
        # 호출(둘 다 이 플래그를 안 보냄)에는 영향 없음.
        admin_bypass_status = (
            bool(user.get("_admin_edit_bypass_status"))
            and user.get("role") == "super_admin"
        )
        if (
            not admin_bypass_status
            and portfolio["status"] not in (
                EDITABLE_PORTFOLIO_STATUSES
            )
        ):
            raise PortfolioStateConflictError(
                "검수 중이거나 공개된 포트폴리오의 "
                "이미지는 변경할 수 없습니다."
            )

        return company, portfolio

    @staticmethod
    def _get_read_context(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        return company, portfolio

    @staticmethod
    def list_images(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> list[dict[str, Any]]:
        CompanyPortfolioImageService._get_read_context(
            session,
            user=user,
            portfolio_id=portfolio_id,
        )

        return repository.list_portfolio_images(
            session,
            portfolio_id=portfolio_id,
        )

    @staticmethod
    async def upload_image(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        room_code: str,
        portfolio_space_id: int | None,
        upload: UploadFile,
        description: str | None = None,
        sort_order_override: int | None = None,
        is_representative_override: bool | None = None,
    ) -> dict[str, Any]:
        # sort_order_override/is_representative_override: 관리자 일괄등록
        # 워커가 같은 포트폴리오의 이미지 여러 장을 동시에(병렬로) 저장할 때만
        # 넘긴다. 기본 계산 방식(next_portfolio_image_sort_order로 "현재
        # 최대값+1"을 그때그때 읽는 것, is_representative를 "현재 개수==0"으로
        # 판단하는 것)은 같은 포트폴리오에 대해 동시에 여러 번 호출되면 여러
        # 이미지가 같은 sort_order를 받거나 대표사진이 중복 지정될 수 있는
        # 경쟁 조건이 있다. 일괄등록 워커는 배치 전체의 최종 순서를 미리
        # 알고 있으므로 각 이미지의 순서를 미리 계산해서 넘겨 이 경쟁을
        # 원천적으로 피한다. 회사 회원이 직접 올리는 일반 업로드는 이 값을
        # 안 넘기므로(한 번에 한 장씩만 순차 업로드) 기존 동작 그대로다.
        company, portfolio = (
            CompanyPortfolioImageService
            ._get_editable_context(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        if room_code not in ALLOWED_ROOM_CODES:
            raise PortfolioImageValidationError(
                "올바르지 않은 공간 분류입니다."
            )

        if portfolio_space_id is not None:
            space = repository.find_portfolio_space(
                session,
                portfolio_id=portfolio_id,
                space_id=portfolio_space_id,
            )

            if space is None:
                raise PortfolioImageValidationError(
                    "선택한 포트폴리오 공간을 찾을 수 없습니다."
                )

            # 신규 공간 구조 사용 시 기존 room_code도 자동 동기화
            room_code = space["space_code"]

        if upload.content_type not in ALLOWED_MIME_TYPES:
            raise PortfolioImageValidationError(
                "JPG, PNG, WEBP 이미지만 "
                "업로드할 수 있습니다."
            )

        current_count = (
            repository.count_portfolio_images(
                session,
                portfolio_id=portfolio_id,
            )
        )

        if current_count >= MAX_IMAGES_PER_PORTFOLIO:
            raise PortfolioImageLimitError(
                "포트폴리오당 이미지는 최대 "
                f"{MAX_IMAGES_PER_PORTFOLIO}개까지 "
                "등록할 수 있습니다."
            )

        file_data = await upload.read(
            MAX_IMAGE_SIZE + 1
        )

        if not file_data:
            raise PortfolioImageValidationError(
                "비어 있는 파일은 업로드할 수 없습니다."
            )

        if len(file_data) > MAX_IMAGE_SIZE:
            raise PortfolioImageValidationError(
                "이미지는 파일당 최대 50MB까지 "
                "업로드할 수 있습니다."
            )

        expected_format, original_extension = (
            ALLOWED_MIME_TYPES[upload.content_type]
        )

        try:
            with Image.open(
                BytesIO(file_data)
            ) as verification_image:
                verification_image.verify()

            with Image.open(
                BytesIO(file_data)
            ) as opened_image:
                detected_format = (
                    opened_image.format or ""
                ).upper()

                if detected_format != expected_format:
                    raise PortfolioImageValidationError(
                        "파일 내용과 이미지 형식이 "
                        "일치하지 않습니다."
                    )

                processed_image = ImageOps.exif_transpose(
                    opened_image
                )
                processed_image.load()

                original_width, original_height = (
                    processed_image.size
                )

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as exc:
            raise PortfolioImageValidationError(
                "정상적인 이미지 파일이 아닙니다."
            ) from exc

        stored_uuid = uuid4()
        stored_filename = str(stored_uuid)

        directories = _prepare_directories(
            portfolio_id
        )

        large_file_path = (
            directories["large"]
            / f"{stored_filename}.webp"
        )
        medium_file_path = (
            directories["medium"]
            / f"{stored_filename}.webp"
        )
        thumbnail_file_path = (
            directories["thumbnail"]
            / f"{stored_filename}.webp"
        )

        created_paths = [
            large_file_path,
            medium_file_path,
            thumbnail_file_path,
        ]

        try:
            large_width, large_height, large_size = (
                _save_webp_variant(
                    processed_image,
                    target_path=large_file_path,
                    max_dimension=1920,
                    quality=88,
                    max_size_bytes=3 * 1024 * 1024,
                )
            )

            medium_width, medium_height, medium_size = (
                _save_webp_variant(
                    processed_image,
                    target_path=medium_file_path,
                    max_dimension=1200,
                    quality=84,
                )
            )

            (
                thumbnail_width,
                thumbnail_height,
                thumbnail_size,
            ) = _save_webp_variant(
                processed_image,
                target_path=thumbnail_file_path,
                max_dimension=480,
                quality=80,
            )

            sort_order = (
                sort_order_override
                if sort_order_override is not None
                else repository.next_portfolio_image_sort_order(
                    session,
                    portfolio_id=portfolio_id,
                )
            )

            is_representative = (
                is_representative_override
                if is_representative_override is not None
                else current_count == 0
            )

            base_url = (
                f"{PORTFOLIO_URL_PREFIX}/"
                f"{portfolio_id}"
            )

            image_id = (
                repository.create_portfolio_image(
                    session=session,
                    portfolio_id=portfolio_id,
                    room_code=room_code,
                    original_filename=(
                        upload.filename or
                        f"image{original_extension}"
                    ),
                    stored_filename=stored_filename,
                    original_mime_type=(
                        upload.content_type
                    ),
                    original_size_bytes=len(file_data),
                    original_width=original_width,
                    original_height=original_height,
                    large_path=(
                        f"{base_url}/large/"
                        f"{stored_filename}.webp"
                    ),
                    large_size_bytes=large_size,
                    large_width=large_width,
                    large_height=large_height,
                    medium_path=(
                        f"{base_url}/medium/"
                        f"{stored_filename}.webp"
                    ),
                    medium_size_bytes=medium_size,
                    medium_width=medium_width,
                    medium_height=medium_height,
                    thumbnail_path=(
                        f"{base_url}/thumbnail/"
                        f"{stored_filename}.webp"
                    ),
                    thumbnail_size_bytes=(
                        thumbnail_size
                    ),
                    thumbnail_width=thumbnail_width,
                    thumbnail_height=thumbnail_height,
                    sort_order=sort_order,
                    is_representative=(
                        is_representative
                    ),
                    description=(
                        description.strip()[:2000]
                        if description and description.strip()
                        else None
                    ),
                )
            )

            if portfolio_space_id is not None:
                repository.set_portfolio_image_space(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                    portfolio_space_id=portfolio_space_id,
                )

            if is_representative:
                repository.set_portfolio_representative_image(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type=(
                    "portfolio.image_uploaded"
                ),
                target_type="portfolio_image",
                target_id=image_id,
                after_data={
                    "portfolio_id": portfolio_id,
                    "room_code": room_code,
                    "portfolio_space_id": portfolio_space_id,
                    "original_filename": (
                        upload.filename
                    ),
                    "original_mime_type": (
                        upload.content_type
                    ),
                    "original_size_bytes": (
                        len(file_data)
                    ),
                    "original_width": original_width,
                    "original_height": original_height,
                    "is_representative": (
                        is_representative
                    ),
                },
                reason="업체 포트폴리오 이미지 등록",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "portfolio_id": portfolio_id,
                    "member_role": (
                        company["member_role"]
                    ),
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name=(
                    "PortfolioImageUploaded"
                ),
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "image_id": image_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "room_code": room_code,
                    "portfolio_space_id": portfolio_space_id,
                    "is_representative": (
                        is_representative
                    ),
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()

            for path in created_paths:
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass

            raise

        image = repository.find_portfolio_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )

        if image is None:
            raise PortfolioImageNotFoundError(
                "등록된 이미지를 조회하지 못했습니다."
            )

        return image

    @staticmethod
    def update_image(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        image_id: int,
        payload: PortfolioImageUpdateRequest,
    ) -> dict[str, Any]:
        company, portfolio = (
            CompanyPortfolioImageService
            ._get_editable_context(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        image = repository.find_portfolio_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )

        if image is None:
            raise PortfolioImageNotFoundError(
                "포트폴리오 이미지를 찾을 수 없습니다."
            )

        changes = payload.model_dump(
            exclude_unset=True
        )

        if not changes:
            raise EmptyPortfolioUpdateError(
                "수정할 이미지 정보가 없습니다."
            )

        if (
            "room_code" in changes
            and changes["room_code"] is None
        ):
            raise PortfolioImageValidationError(
                "공간 분류는 비울 수 없습니다."
            )

        before_data = {
            key: image.get(key)
            for key in changes
        }

        try:
            updated = (
                repository
                .update_portfolio_image_metadata(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                    changes=changes,
                )
            )

            if not updated:
                raise PortfolioImageNotFoundError(
                    "이미지 정보를 수정하지 못했습니다."
                )

            updated_image = (
                repository.find_portfolio_image(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                )
            )

            if updated_image is None:
                raise PortfolioImageNotFoundError(
                    "수정된 이미지를 조회하지 못했습니다."
                )

            after_data = {
                key: updated_image.get(key)
                for key in changes
            }

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type=(
                    "portfolio.image_updated"
                ),
                target_type="portfolio_image",
                target_id=image_id,
                before_data=before_data,
                after_data=after_data,
                reason=(
                    "업체 포트폴리오 이미지 정보 수정"
                ),
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "portfolio_id": portfolio_id,
                    "changed_fields": sorted(changes),
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name=(
                    "PortfolioImageUpdated"
                ),
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "image_id": image_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "changed_fields": sorted(changes),
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return updated_image

    @staticmethod
    def move_image_to_space(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        image_id: int,
        portfolio_space_id: int,
    ) -> dict[str, Any]:
        company, portfolio = (
            CompanyPortfolioImageService
            ._get_editable_context(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        image = repository.find_portfolio_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )

        if image is None:
            raise PortfolioImageNotFoundError(
                "포트폴리오 이미지를 찾을 수 없습니다."
            )

        space = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=portfolio_space_id,
        )

        if space is None:
            raise PortfolioImageValidationError(
                "선택한 포트폴리오 공간을 찾을 수 없습니다."
            )

        before_data = {
            "portfolio_space_id": image.get(
                "portfolio_space_id"
            ),
            "room_code": image.get("room_code"),
        }

        try:
            repository.set_portfolio_image_space(
                session,
                portfolio_id=portfolio_id,
                image_id=image_id,
                portfolio_space_id=portfolio_space_id,
            )

            repository.update_portfolio_image_metadata(
                session,
                portfolio_id=portfolio_id,
                image_id=image_id,
                changes={
                    "room_code": space["space_code"],
                },
            )

            updated_image = repository.find_portfolio_image(
                session,
                portfolio_id=portfolio_id,
                image_id=image_id,
            )

            if updated_image is None:
                raise PortfolioImageNotFoundError(
                    "이동된 이미지를 조회하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.image_space_moved",
                target_type="portfolio_image",
                target_id=image_id,
                before_data=before_data,
                after_data={
                    "portfolio_space_id": portfolio_space_id,
                    "room_code": space["space_code"],
                },
                reason="업체 포트폴리오 이미지 공간 이동",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "portfolio_id": portfolio_id,
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioImageSpaceMoved",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "image_id": image_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "portfolio_space_id": portfolio_space_id,
                    "room_code": space["space_code"],
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()
            return updated_image

        except Exception:
            session.rollback()
            raise


    @staticmethod
    def set_representative(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        image_id: int,
    ) -> dict[str, Any]:
        company, portfolio = (
            CompanyPortfolioImageService
            ._get_editable_context(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        image = repository.find_portfolio_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )

        if image is None:
            raise PortfolioImageNotFoundError(
                "포트폴리오 이미지를 찾을 수 없습니다."
            )

        previous_representative_id = (
            portfolio.get("representative_image_id")
        )

        try:
            repository.clear_portfolio_representative_images(
                session,
                portfolio_id=portfolio_id,
            )

            changed = (
                repository
                .set_portfolio_representative_image(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                )
            )

            if not changed:
                raise PortfolioImageNotFoundError(
                    "대표 이미지를 설정하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type=(
                    "portfolio.representative_image_set"
                ),
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "representative_image_id": (
                        previous_representative_id
                    ),
                },
                after_data={
                    "representative_image_id": image_id,
                },
                reason="업체 포트폴리오 대표 이미지 변경",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name=(
                    "PortfolioRepresentativeImageSet"
                ),
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "image_id": image_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
            "representative_image_id": image_id,
            "message": (
                "포트폴리오 대표 이미지가 "
                "설정되었습니다."
            ),
        }

    @staticmethod
    def delete_image(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        image_id: int,
    ) -> dict[str, Any]:
        company, portfolio = (
            CompanyPortfolioImageService
            ._get_editable_context(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        image = repository.find_portfolio_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
        )

        if image is None:
            raise PortfolioImageNotFoundError(
                "포트폴리오 이미지를 찾을 수 없습니다."
            )

        was_representative = bool(
            image["is_representative"]
            or portfolio.get(
                "representative_image_id"
            ) == image_id
        )

        try:
            if was_representative:
                repository.clear_portfolio_representative_image_reference(
                    session,
                    portfolio_id=portfolio_id,
                    image_id=image_id,
                )

            deleted = repository.delete_portfolio_image(
                session,
                portfolio_id=portfolio_id,
                image_id=image_id,
            )

            if not deleted:
                raise PortfolioImageNotFoundError(
                    "포트폴리오 이미지를 "
                    "삭제하지 못했습니다."
                )

            promoted_image_id = None

            if was_representative:
                promoted_image_id = (
                    repository
                    .promote_first_portfolio_image(
                        session,
                        portfolio_id=portfolio_id,
                    )
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type=(
                    "portfolio.image_deleted"
                ),
                target_type="portfolio_image",
                target_id=image_id,
                before_data={
                    "portfolio_id": portfolio_id,
                    "room_code": image["room_code"],
                    "original_filename": (
                        image["original_filename"]
                    ),
                    "is_representative": (
                        was_representative
                    ),
                },
                after_data={
                    "deleted": True,
                    "promoted_image_id": (
                        promoted_image_id
                    ),
                },
                reason="업체 포트폴리오 이미지 삭제",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "portfolio_id": portfolio_id,
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name=(
                    "PortfolioImageDeleted"
                ),
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "image_id": image_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "promoted_image_id": (
                        promoted_image_id
                    ),
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        _remove_image_files(image)

        return {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
            "message": (
                "포트폴리오 이미지가 삭제되었습니다."
            ),
        }


def save_admin_imported_image(
    session: Session,
    *,
    admin_user_id: int,
    company_id: int,
    portfolio_id: int,
    room_code: str,
    portfolio_space_id: int | None,
    original_filename: str,
    content_type: str,
    file_data: bytes,
    description: str | None = None,
    sort_order_override: int | None = None,
    is_representative_override: bool | None = None,
    bypass_editable_status: bool = False,
) -> dict[str, Any]:
    """관리자 일괄등록 이미지를 기존 업체 업로드 경로와 동일하게 처리한다.
    sort_order_override/is_representative_override는 같은 포트폴리오의
    이미지를 병렬로 저장할 때만 넘긴다 -- upload_image의 관련 설명 참고.
    bypass_editable_status=True는 이미 승인·공개된 포트폴리오에도 이미지를
    추가할 수 있게 한다(관리자 "원본대조·수정" 화면과 같은 플래그) --
    v2.5.1 content_blocks 로컬화 백필처럼, 기존 사진을 바꾸는 게 아니라
    "본문에는 나오는데 우리 서버엔 없던 사진"을 채워 넣기만 하는 관리자
    보정 작업에서만 켠다. 일반 대량등록 흐름은 기본값(False)을 그대로
    쓰므로 검수 전 상태에서만 이미지가 붙는 기존 동작과 동일하다."""
    upload = UploadFile(
        file=BytesIO(file_data),
        size=len(file_data),
        filename=original_filename,
        headers=Headers({"content-type": content_type}),
    )
    return asyncio.run(
        CompanyPortfolioImageService.upload_image(
            session,
            user={
                "id": admin_user_id,
                "role": "super_admin",
                "_bulk_import_company_id": company_id,
                "_admin_edit_bypass_status": bypass_editable_status,
            },
            portfolio_id=portfolio_id,
            room_code=room_code,
            portfolio_space_id=portfolio_space_id,
            upload=upload,
            description=description,
            sort_order_override=sort_order_override,
            is_representative_override=is_representative_override,
        )
    )
