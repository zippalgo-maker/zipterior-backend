# 모바일 앱 셸(m.html) 홈 상단 소개 배너 슬라이드 (2026-08-24).
# 사용자 요청: 매번 홈 화면 상단(검색창 아래)에 노출되는 슬라이드,
# 이미지+이동 링크, 관리자가 이미지 업로드로 설정.
#
# 새 테이블을 만들지 않고 기존 `system_features`(feature_key 하나당
# JSONB settings 하나, feature_flags 모듈이 이미 이 패턴으로
# "포트폴리오 하단 안내 이미지" 등에 쓰고 있음)를 그대로 재사용한다 --
# 슬라이드 배열을 settings.slides 안에 통째로 저장. 개별 슬라이드는
# uuid로 식별.
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db


FEATURE_KEY = "mobile_intro_slides"
SLIDE_IMAGE_ROOT = Path("/var/www/zipterior/uploads/mobile-intro-slides")
SLIDE_IMAGE_URL_PREFIX = "/uploads/mobile-intro-slides"
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_SLIDE_IMAGE_SIZE = 5 * 1024 * 1024
MAX_SLIDES = 8

public_router = APIRouter(prefix="/api/v1/public", tags=["public-settings"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-settings"])


def _detect_extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _ensure_feature_row(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO system_features(feature_key, display_name, settings)
            VALUES(:key, '모바일 소개 슬라이드', '{"slides": []}'::jsonb)
            ON CONFLICT (feature_key) DO NOTHING
            """
        ),
        {"key": FEATURE_KEY},
    )


def _load_slides(session: Session) -> list[dict[str, Any]]:
    row = session.execute(
        text("SELECT settings FROM system_features WHERE feature_key=:key"),
        {"key": FEATURE_KEY},
    ).mappings().one_or_none()
    slides = (row["settings"] or {}).get("slides") if row else []
    return list(slides or [])


def _save_slides(session: Session, slides: list[dict[str, Any]], updated_by: int) -> None:
    # 인자로 받은 리스트 "순서"를 그대로 정답으로 삼아 sort_order를
    # 0..n-1로 다시 매긴다 -- 기존 sort_order 값 기준으로 다시
    # sorted()를 걸면(예전 버그) admin_move_slide()가 리스트 순서만
    # 바꾸고 sort_order 필드는 안 바꾸는 방식과 충돌해서 이동이 저장
    # 직후 원래대로 되돌아가 버렸다(2026-08-24 curl로 직접 재현·확인).
    # 호출하는 쪽(생성/삭제/이동)이 이미 리스트를 원하는 최종 순서로
    # 만들어서 넘긴다는 게 이 함수의 전제.
    for index, slide in enumerate(slides):
        slide["sort_order"] = index
    session.execute(
        text(
            """
            UPDATE system_features
            SET settings = jsonb_set(settings, '{slides}', CAST(:slides AS jsonb)),
                updated_by = :updated_by,
                updated_at = now()
            WHERE feature_key = :key
            """
        ),
        {"slides": json.dumps(slides), "updated_by": updated_by, "key": FEATURE_KEY},
    )


def _find_slide(slides: list[dict[str, Any]], slide_id: str) -> dict[str, Any] | None:
    return next((s for s in slides if s.get("id") == slide_id), None)


@public_router.get("/mobile-intro-slides")
def public_list_slides(session: Session = Depends(get_db)):
    slides = [s for s in _load_slides(session) if s.get("is_active")]
    slides.sort(key=lambda s: s.get("sort_order", 0))
    return {
        "items": [
            {
                "id": s["id"],
                "imageUrl": s["image_path"],
                "linkUrl": s.get("link_url") or None,
            }
            for s in slides
        ]
    }


@admin_router.get("/mobile-intro-slides")
def admin_list_slides(current_admin: CurrentAdmin, session: Session = Depends(get_db)):
    slides = sorted(_load_slides(session), key=lambda s: s.get("sort_order", 0))
    return {
        "items": [
            {
                "id": s["id"],
                "imageUrl": s["image_path"],
                "linkUrl": s.get("link_url") or "",
                "isActive": bool(s.get("is_active", True)),
                "sortOrder": s.get("sort_order", 0),
            }
            for s in slides
        ]
    }


@admin_router.post("/mobile-intro-slides", status_code=status.HTTP_201_CREATED)
async def admin_create_slide(
    current_admin: CurrentAdmin,
    upload: UploadFile = File(...),
    link_url: str | None = Form(None),
    session: Session = Depends(get_db),
):
    if upload.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(422, "JPG, PNG, WEBP 이미지만 업로드할 수 있습니다.")
    data = await upload.read(MAX_SLIDE_IMAGE_SIZE + 1)
    if not data:
        raise HTTPException(422, "빈 파일은 업로드할 수 없습니다.")
    if len(data) > MAX_SLIDE_IMAGE_SIZE:
        raise HTTPException(413, "이미지는 최대 5MB까지 업로드할 수 있습니다.")
    detected = _detect_extension(data)
    if detected is None or detected != ALLOWED_MIME_TYPES[upload.content_type]:
        raise HTTPException(422, "올바른 이미지 파일이 아닙니다.")

    _ensure_feature_row(session)
    slides = _load_slides(session)
    if len(slides) >= MAX_SLIDES:
        raise HTTPException(422, f"슬라이드는 최대 {MAX_SLIDES}개까지 등록할 수 있습니다. 기존 슬라이드를 삭제한 뒤 다시 시도해 주세요.")

    SLIDE_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{detected}"
    target_path = SLIDE_IMAGE_ROOT / filename
    image_path = f"{SLIDE_IMAGE_URL_PREFIX}/{filename}"
    target_path.write_bytes(data)

    slide = {
        "id": uuid4().hex,
        "image_path": image_path,
        "link_url": (link_url or "").strip() or None,
        "is_active": True,
        "sort_order": len(slides),
    }
    slides.append(slide)
    try:
        _save_slides(session, slides, current_admin["id"])
        session.commit()
    except Exception:
        session.rollback()
        target_path.unlink(missing_ok=True)
        raise
    return {
        "id": slide["id"],
        "imageUrl": slide["image_path"],
        "linkUrl": slide["link_url"] or "",
        "isActive": True,
        "sortOrder": slide["sort_order"],
    }


class SlideUpdateRequest(BaseModel):
    link_url: str | None = None
    is_active: bool | None = None


@admin_router.patch("/mobile-intro-slides/{slide_id}")
def admin_update_slide(
    slide_id: str,
    payload: SlideUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
):
    slides = _load_slides(session)
    slide = _find_slide(slides, slide_id)
    if not slide:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다.")
    patch = payload.model_dump(exclude_unset=True)
    if "link_url" in patch:
        slide["link_url"] = (patch["link_url"] or "").strip() or None
    if "is_active" in patch:
        slide["is_active"] = bool(patch["is_active"])
    _save_slides(session, slides, current_admin["id"])
    session.commit()
    return {
        "id": slide["id"],
        "imageUrl": slide["image_path"],
        "linkUrl": slide.get("link_url") or "",
        "isActive": bool(slide.get("is_active", True)),
        "sortOrder": slide.get("sort_order", 0),
    }


class SlideMoveRequest(BaseModel):
    direction: str


@admin_router.post("/mobile-intro-slides/{slide_id}/move")
def admin_move_slide(
    slide_id: str,
    payload: SlideMoveRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
):
    if payload.direction not in ("up", "down"):
        raise HTTPException(422, "direction은 up 또는 down이어야 합니다.")
    slides = sorted(_load_slides(session), key=lambda s: s.get("sort_order", 0))
    index = next((i for i, s in enumerate(slides) if s.get("id") == slide_id), None)
    if index is None:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다.")
    target = index - 1 if payload.direction == "up" else index + 1
    if target < 0 or target >= len(slides):
        return {"moved": False}
    slides[index], slides[target] = slides[target], slides[index]
    _save_slides(session, slides, current_admin["id"])
    session.commit()
    return {"moved": True}


@admin_router.delete("/mobile-intro-slides/{slide_id}")
def admin_delete_slide(
    slide_id: str,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
):
    slides = _load_slides(session)
    slide = _find_slide(slides, slide_id)
    if not slide:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다.")
    remaining = [s for s in slides if s.get("id") != slide_id]
    _save_slides(session, remaining, current_admin["id"])
    session.commit()
    image_path = slide.get("image_path") or ""
    filename = image_path.rsplit("/", 1)[-1] if image_path else ""
    if filename:
        (SLIDE_IMAGE_ROOT / filename).unlink(missing_ok=True)
    return {"deleted": True}
