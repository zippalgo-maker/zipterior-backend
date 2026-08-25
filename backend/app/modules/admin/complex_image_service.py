from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
COMPLEX_IMAGE_ROOT = Path("/var/www/zipterior/uploads/complexes")


class ComplexImageProcessor:
    """단지 사진을 실제 디코딩해 검증하고 공개용 WebP 두 종류로 저장한다."""

    @staticmethod
    async def save(upload: UploadFile, *, complex_id: int) -> dict:
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        if not data:
            raise ValueError("업로드할 단지 이미지가 비어 있습니다.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("단지 이미지는 파일당 10MB 이하만 업로드할 수 있습니다.")

        try:
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError(
                        "단지 이미지는 JPG, PNG, WEBP 형식만 업로드할 수 있습니다."
                    )
                source.verify()
            with Image.open(BytesIO(data)) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError("단지 이미지 해상도가 너무 큽니다.")
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("JPG, PNG, WEBP 형식의 정상 이미지 파일만 업로드할 수 있습니다.") from exc

        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        thumbnail = image.copy()
        thumbnail.thumbnail((640, 640), Image.Resampling.LANCZOS)

        directory = COMPLEX_IMAGE_ROOT / str(complex_id)
        directory.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        image_file = directory / f"{token}.webp"
        thumbnail_file = directory / f"{token}-thumb.webp"
        image.save(image_file, "WEBP", quality=88, method=6)
        thumbnail.save(thumbnail_file, "WEBP", quality=82, method=6)

        return {
            "image_path": f"/uploads/complexes/{complex_id}/{image_file.name}",
            "thumbnail_path": f"/uploads/complexes/{complex_id}/{thumbnail_file.name}",
            "width": image.width,
            "height": image.height,
            "size_bytes": image_file.stat().st_size,
            "files": (image_file, thumbnail_file),
        }

    @staticmethod
    def remove_files(*paths: str) -> None:
        # DB에 저장된 단지 업로드 경로만 지워 임의 경로 삭제를 차단한다.
        public_root = Path("/var/www/zipterior")
        for path in paths:
            if path and path.startswith("/uploads/complexes/"):
                (public_root / path.lstrip("/")).unlink(missing_ok=True)
