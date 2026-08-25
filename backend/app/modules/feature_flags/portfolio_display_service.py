"""v2.5.1: 포트폴리오 상세 하단 표시 설정(SNS링크 노출 + 안내문구/CTA)
전용 서비스. feature_flags.repository의 system_features 접근 함수를
그대로 재사용한다. V2.5.0_PLAN.md 참고."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.modules.feature_flags import repository
from app.modules.feature_flags.schemas import DEFAULT_NOTICE_BUTTON_LABEL

SNS_LINKS_KEY = "portfolio_bottom_sns_links"
NOTICE_KEY = "portfolio_bottom_notice"

NOTICE_IMAGE_ROOT = Path("/var/www/zipterior/uploads/site-settings")
NOTICE_IMAGE_URL_PREFIX = "/uploads/site-settings"
MAX_NOTICE_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class InvalidNoticeImageError(ValueError):
    pass


def _detect_extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _remove_managed_notice_image(image_path: str | None) -> None:
    if not image_path or not image_path.startswith(f"{NOTICE_IMAGE_URL_PREFIX}/"):
        return
    filename = image_path.removeprefix(f"{NOTICE_IMAGE_URL_PREFIX}/")
    if not filename or "/" in filename or "\\" in filename:
        return
    target = NOTICE_IMAGE_ROOT / filename
    if target.exists() and target.is_file():
        target.unlink()


class PortfolioDisplaySettingsService:
    @staticmethod
    def get(session: Session) -> dict[str, Any]:
        sns = repository.get_base_feature(session, SNS_LINKS_KEY) or {
            "is_enabled": False,
        }
        notice = repository.get_base_feature(session, NOTICE_KEY) or {
            "is_enabled": True,
            "settings": {},
        }
        notice_settings = notice.get("settings") or {}
        return {
            "sns_links_enabled": bool(sns["is_enabled"]),
            "notice_enabled": bool(notice["is_enabled"]),
            "notice_text": notice_settings.get("text") or None,
            "notice_image_path": notice_settings.get("image_path"),
            "notice_button_label": (
                notice_settings.get("button_label") or DEFAULT_NOTICE_BUTTON_LABEL
            ),
        }

    @staticmethod
    def update(
        session: Session,
        *,
        admin_user_id: int,
        sns_links_enabled: bool | None,
        notice_enabled: bool | None,
        notice_text: str | None,
        notice_button_label: str | None,
    ) -> dict[str, Any]:
        if sns_links_enabled is not None:
            repository.set_feature_enabled(
                session,
                feature_key=SNS_LINKS_KEY,
                is_enabled=sns_links_enabled,
                updated_by=admin_user_id,
            )
        if notice_enabled is not None:
            repository.set_feature_enabled(
                session,
                feature_key=NOTICE_KEY,
                is_enabled=notice_enabled,
                updated_by=admin_user_id,
            )
        patch: dict[str, Any] = {}
        if notice_text is not None:
            patch["text"] = notice_text
        if notice_button_label is not None:
            patch["button_label"] = notice_button_label
        if patch:
            repository.merge_feature_settings(
                session,
                feature_key=NOTICE_KEY,
                patch=patch,
                updated_by=admin_user_id,
            )
        session.commit()
        return PortfolioDisplaySettingsService.get(session)

    @staticmethod
    async def upload_notice_image(
        session: Session,
        *,
        admin_user_id: int,
        upload: UploadFile,
    ) -> dict[str, Any]:
        if upload.content_type not in ALLOWED_MIME_TYPES:
            raise InvalidNoticeImageError("JPG, PNG, WEBP 이미지만 업로드할 수 있습니다.")
        data = await upload.read(MAX_NOTICE_IMAGE_SIZE + 1)
        if not data:
            raise InvalidNoticeImageError("비어 있는 파일은 업로드할 수 없습니다.")
        if len(data) > MAX_NOTICE_IMAGE_SIZE:
            raise InvalidNoticeImageError("이미지는 최대 5MB까지 업로드할 수 있습니다.")
        detected = _detect_extension(data)
        if detected is None:
            raise InvalidNoticeImageError("올바른 이미지 파일이 아닙니다.")
        if detected != ALLOWED_MIME_TYPES[upload.content_type]:
            raise InvalidNoticeImageError("파일 내용과 이미지 형식이 일치하지 않습니다.")

        NOTICE_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
        filename = f"portfolio_notice_{uuid4().hex}{detected}"
        target_path = NOTICE_IMAGE_ROOT / filename
        image_path = f"{NOTICE_IMAGE_URL_PREFIX}/{filename}"

        existing = repository.get_base_feature(session, NOTICE_KEY)
        old_path = (existing.get("settings") or {}).get("image_path") if existing else None

        target_path.write_bytes(data)
        repository.merge_feature_settings(
            session,
            feature_key=NOTICE_KEY,
            patch={"image_path": image_path},
            updated_by=admin_user_id,
        )
        session.commit()
        _remove_managed_notice_image(old_path)
        return {"notice_image_path": image_path}

    @staticmethod
    def delete_notice_image(session: Session, *, admin_user_id: int) -> dict[str, Any]:
        existing = repository.get_base_feature(session, NOTICE_KEY)
        old_path = (existing.get("settings") or {}).get("image_path") if existing else None
        repository.merge_feature_settings(
            session,
            feature_key=NOTICE_KEY,
            patch={"image_path": None},
            updated_by=admin_user_id,
        )
        session.commit()
        _remove_managed_notice_image(old_path)
        return {"notice_image_path": None}
