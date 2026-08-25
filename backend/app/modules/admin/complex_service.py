from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.admin import complex_repository as repository
from app.modules.admin.complex_image_service import ComplexImageProcessor


class AdminComplexNotFoundError(ValueError):
    pass


class AdminApartmentTypeNotFoundError(ValueError):
    pass


class AdminApartmentTypeInUseError(ValueError):
    pass


class AdminComplexDuplicateError(ValueError):
    pass


class AdminComplexImageNotFoundError(ValueError):
    pass


class AdminComplexService:
    @staticmethod
    def list_complexes(
        session: Session,
        *,
        q: str | None,
        sido: str | None,
        sigungu: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        items = repository.list_complexes(
            session,
            q=q,
            sido=sido,
            sigungu=sigungu,
            limit=limit,
            offset=offset,
        )
        total = repository.count_complexes(
            session,
            q=q,
            sido=sido,
            sigungu=sigungu,
        )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def get_complex(
        session: Session,
        *,
        complex_id: int,
    ) -> dict[str, Any]:
        complex_data = repository.find_complex(
            session,
            complex_id,
        )

        if complex_data is None:
            raise AdminComplexNotFoundError(
                "단지를 찾을 수 없습니다."
            )

        complex_data["apartment_types"] = (
            repository.list_apartment_types(
                session,
                complex_id=complex_id,
            )
        )
        complex_data["images"] = repository.list_complex_images(
            session, complex_id=complex_id
        )

        return complex_data

    @staticmethod
    def create_complex(
        session: Session,
        *,
        admin_user_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        duplicate = repository.find_duplicate_complex(
            session,
            name=values["name"],
            road_address=values.get("road_address"),
        )
        if duplicate:
            raise AdminComplexDuplicateError(
                f"이미 등록된 단지입니다. ({duplicate['name']} #{duplicate['id']})"
            )
        try:
            complex_id = repository.create_complex(
                session,
                values=values,
            )

            session.commit()

        except IntegrityError as exc:
            session.rollback()
            raise AdminComplexDuplicateError("이미 등록된 단지입니다.") from exc
        except Exception:
            session.rollback()
            raise

        return {
            "id": complex_id,
            "message": "단지가 등록되었습니다.",
        }

    @staticmethod
    def create_complex_with_types(
        session: Session,
        *,
        admin_user_id: int,
        values: dict[str, Any],
        apartment_types: list[dict[str, Any]],
    ) -> dict[str, Any]:
        duplicate = repository.find_duplicate_complex(
            session,
            name=values["name"],
            road_address=values.get("road_address"),
        )
        if duplicate:
            raise AdminComplexDuplicateError(
                f"이미 등록된 단지입니다. ({duplicate['name']} #{duplicate['id']})"
            )
        try:
            complex_id = repository.create_complex(
                session,
                values=values,
            )

            type_ids = []

            for type_values in apartment_types:
                type_id = repository.create_apartment_type(
                    session,
                    complex_id=complex_id,
                    values=type_values,
                )
                type_ids.append(type_id)

            session.commit()

        except IntegrityError as exc:
            session.rollback()
            raise AdminComplexDuplicateError("이미 등록된 단지입니다.") from exc
        except Exception:
            session.rollback()
            raise

        return {
            "id": complex_id,
            "apartment_type_ids": type_ids,
            "message": "단지와 아파트 타입이 등록되었습니다.",
        }

    @staticmethod
    def update_complex(
        session: Session,
        *,
        complex_id: int,
        admin_user_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        current = repository.find_complex(
            session,
            complex_id,
        )

        if current is None:
            raise AdminComplexNotFoundError(
                "단지를 찾을 수 없습니다."
            )

        duplicate = repository.find_duplicate_complex(
            session,
            name=values["name"],
            road_address=values.get("road_address"),
            exclude_id=complex_id,
        )
        if duplicate:
            raise AdminComplexDuplicateError(
                f"이미 등록된 단지입니다. ({duplicate['name']} #{duplicate['id']})"
            )
        try:
            updated = repository.update_complex(
                session,
                complex_id=complex_id,
                values=values,
            )

            if not updated:
                raise AdminComplexNotFoundError(
                    "단지 정보를 수정하지 못했습니다."
                )

            session.commit()

        except IntegrityError as exc:
            session.rollback()
            raise AdminComplexDuplicateError("이미 등록된 단지입니다.") from exc
        except Exception:
            session.rollback()
            raise

        return {
            "id": complex_id,
            "message": "단지 기본정보가 수정되었습니다.",
        }

    @staticmethod
    def refresh_from_naver(
        session: Session,
        *,
        complex_id: int,
        naver_data: dict[str, Any],
    ) -> dict[str, Any]:
        """기존 타입 ID는 같은 타입에 유지하고 전체 교체를 한 트랜잭션으로 끝낸다."""
        current = repository.find_complex(session, complex_id)
        if current is None:
            raise AdminComplexNotFoundError("단지를 찾을 수 없습니다.")

        existing_types = repository.list_apartment_types(
            session, complex_id=complex_id
        )
        incoming_types = naver_data.get("apartment_types") or []
        normalize = lambda value: "".join(
            character.lower() for character in str(value or "")
            if character.isalnum()
        )
        existing_by_name = {
            normalize(item.get("type_name")): item for item in existing_types
            if normalize(item.get("type_name"))
        }
        incoming_names = {
            normalize(item.get("type_name")) for item in incoming_types
            if normalize(item.get("type_name"))
        }

        # 연결된 타입을 없애는 재수집은 FK를 깨뜨리지 않고 관리자에게 먼저 알린다.
        if incoming_types:
            for item in existing_types:
                if normalize(item.get("type_name")) in incoming_names:
                    continue
                references = repository.count_type_references(
                    session, type_id=item["id"]
                )
                if references["portfolio_count"] or references["estimate_count"]:
                    raise AdminApartmentTypeInUseError(
                        "포트폴리오 또는 견적에 연결된 기존 타입이 네이버 결과에 없어 "
                        "자동 교체할 수 없습니다. 연결 데이터를 먼저 확인해 주세요."
                    )

        basic_values = {
            key: naver_data.get(key)
            for key in (
                "completion_year", "household_count", "building_count",
                "parking_count", "heating_type", "builder_name",
            )
        }
        try:
            repository.update_complex(
                session, complex_id=complex_id, values=basic_values
            )
            if incoming_types:
                for sort_order, item in enumerate(incoming_types):
                    values = {
                        "type_name": item.get("type_name"),
                        "supply_area_m2": item.get("supply_area_m2"),
                        "exclusive_area_m2": item.get("exclusive_area_m2"),
                        "pyeong_label": item.get("pyeong_label"),
                        "room_count": item.get("room_count"),
                        "bathroom_count": item.get("bathroom_count"),
                        "has_basic_layout": item.get("has_basic_layout"),
                        "has_expanded_layout": item.get("has_expanded_layout"),
                        "sort_order": sort_order,
                    }
                    matched = existing_by_name.get(normalize(item.get("type_name")))
                    if matched:
                        repository.update_apartment_type(
                            session,
                            complex_id=complex_id,
                            type_id=matched["id"],
                            values=values,
                        )
                    else:
                        repository.create_apartment_type(
                            session,
                            complex_id=complex_id,
                            values={**values, "floor_plan_path": None},
                        )
                for item in existing_types:
                    if normalize(item.get("type_name")) not in incoming_names:
                        repository.delete_apartment_type(
                            session, complex_id=complex_id, type_id=item["id"]
                        )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return AdminComplexService.get_complex(session, complex_id=complex_id)

    @staticmethod
    async def upload_complex_image(
        session: Session,
        *,
        complex_id: int,
        upload: UploadFile,
    ) -> dict[str, Any]:
        if repository.find_complex(session, complex_id) is None:
            raise AdminComplexNotFoundError("단지를 찾을 수 없습니다.")
        if len(repository.list_complex_images(session, complex_id=complex_id)) >= 10:
            raise ValueError("단지 이미지는 최대 10장까지 등록할 수 있습니다.")

        processed = await ComplexImageProcessor.save(upload, complex_id=complex_id)
        files = processed.pop("files")
        try:
            image_id = repository.create_complex_image(
                session, complex_id=complex_id, values=processed
            )
            image = repository.find_complex_image(
                session, complex_id=complex_id, image_id=image_id
            )
            if image and image["is_representative"]:
                repository.set_representative_complex_image(
                    session, complex_id=complex_id, image_id=image_id
                )
            session.commit()
        except Exception:
            session.rollback()
            for file in files:
                file.unlink(missing_ok=True)
            raise
        return repository.find_complex_image(
            session, complex_id=complex_id, image_id=image_id
        )

    @staticmethod
    def set_representative_image(
        session: Session,
        *,
        complex_id: int,
        image_id: int,
    ) -> dict[str, Any]:
        if not repository.set_representative_complex_image(
            session, complex_id=complex_id, image_id=image_id
        ):
            raise AdminComplexImageNotFoundError("단지 이미지를 찾을 수 없습니다.")
        session.commit()
        return repository.find_complex_image(
            session, complex_id=complex_id, image_id=image_id
        )

    @staticmethod
    def delete_complex_image(
        session: Session,
        *,
        complex_id: int,
        image_id: int,
    ) -> dict[str, Any]:
        image = repository.find_complex_image(
            session, complex_id=complex_id, image_id=image_id
        )
        if image is None:
            raise AdminComplexImageNotFoundError("단지 이미지를 찾을 수 없습니다.")
        try:
            repository.delete_complex_image(
                session, complex_id=complex_id, image_id=image_id
            )
            if image["is_representative"]:
                next_id = repository.select_first_complex_image_id(
                    session, complex_id=complex_id
                )
                if next_id is None:
                    repository.clear_representative_complex_image(
                        session, complex_id=complex_id
                    )
                else:
                    repository.set_representative_complex_image(
                        session, complex_id=complex_id, image_id=next_id
                    )
            session.commit()
        except Exception:
            session.rollback()
            raise
        ComplexImageProcessor.remove_files(
            image["image_path"], image["thumbnail_path"]
        )
        return {"id": image_id, "message": "단지 이미지가 삭제되었습니다."}

    @staticmethod
    def create_apartment_type(
        session: Session,
        *,
        complex_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        complex_data = repository.find_complex(
            session,
            complex_id,
        )

        if complex_data is None:
            raise AdminComplexNotFoundError(
                "단지를 찾을 수 없습니다."
            )

        try:
            type_id = repository.create_apartment_type(
                session,
                complex_id=complex_id,
                values=values,
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "id": type_id,
            "message": "면적·타입 정보가 등록되었습니다.",
        }

    @staticmethod
    def update_apartment_type(
        session: Session,
        *,
        complex_id: int,
        type_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        current = repository.find_apartment_type(
            session,
            complex_id=complex_id,
            type_id=type_id,
        )

        if current is None:
            raise AdminApartmentTypeNotFoundError(
                "면적·타입 정보를 찾을 수 없습니다."
            )

        try:
            updated = repository.update_apartment_type(
                session,
                complex_id=complex_id,
                type_id=type_id,
                values=values,
            )

            if not updated:
                raise AdminApartmentTypeNotFoundError(
                    "면적·타입 정보를 수정하지 못했습니다."
                )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "id": type_id,
            "message": "면적·타입 정보가 수정되었습니다.",
        }


    @staticmethod
    async def upload_apartment_type_floor_plan(
        session: Session,
        *,
        complex_id: int,
        type_id: int,
        upload: UploadFile,
    ) -> dict[str, Any]:
        current = repository.find_apartment_type(
            session,
            complex_id=complex_id,
            type_id=type_id,
        )

        if current is None:
            raise AdminApartmentTypeNotFoundError(
                "면적·타입 정보를 찾을 수 없습니다."
            )

        allowed = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }

        content_type = (upload.content_type or "").lower()

        if content_type not in allowed:
            raise ValueError(
                "평면도는 JPG, PNG, WEBP 이미지만 업로드할 수 있습니다."
            )

        data = await upload.read(10 * 1024 * 1024 + 1)

        if not data:
            raise ValueError("업로드할 평면도 이미지가 비어 있습니다.")

        if len(data) > 10 * 1024 * 1024:
            raise ValueError("평면도 이미지는 10MB 이하만 업로드할 수 있습니다.")

        root = Path("/var/www/zipterior/uploads/floor-plans")
        root.mkdir(parents=True, exist_ok=True)

        filename = (
            f"complex-{complex_id}-type-{type_id}-"
            f"{uuid4().hex}{allowed[content_type]}"
        )

        target = root / filename
        target.write_bytes(data)

        url = f"/uploads/floor-plans/{filename}"

        old_path = current.get("floor_plan_path")

        try:
            updated = repository.update_apartment_type(
                session,
                complex_id=complex_id,
                type_id=type_id,
                values={"floor_plan_path": url},
            )

            if not updated:
                raise AdminApartmentTypeNotFoundError(
                    "평면도 정보를 저장하지 못했습니다."
                )

            session.commit()

        except Exception:
            session.rollback()
            target.unlink(missing_ok=True)
            raise

        if (
            old_path
            and old_path.startswith("/uploads/floor-plans/")
            and old_path != url
        ):
            old_file = Path("/var/www/zipterior") / old_path.lstrip("/")
            old_file.unlink(missing_ok=True)

        return {
            "id": type_id,
            "floor_plan_path": url,
            "message": "평면도가 등록되었습니다.",
        }


    @staticmethod
    def delete_apartment_type(
        session: Session,
        *,
        complex_id: int,
        type_id: int,
    ) -> dict[str, Any]:
        current = repository.find_apartment_type(
            session,
            complex_id=complex_id,
            type_id=type_id,
        )

        if current is None:
            raise AdminApartmentTypeNotFoundError(
                "면적·타입 정보를 찾을 수 없습니다."
            )

        references = repository.count_type_references(
            session,
            type_id=type_id,
        )

        type_count = repository.count_apartment_types(
            session,
            complex_id=complex_id,
        )

        if type_count <= 1:
            raise AdminApartmentTypeInUseError(
                "단지에는 최소 1개의 아파트 타입이 필요하여 "
                "마지막 타입은 삭제할 수 없습니다."
            )

        if (
            references["portfolio_count"] > 0
            or references["estimate_count"] > 0
        ):
            raise AdminApartmentTypeInUseError(
                "현재 포트폴리오 또는 견적에 사용 중인 "
                "면적·타입은 삭제할 수 없습니다."
            )

        try:
            deleted = repository.delete_apartment_type(
                session,
                complex_id=complex_id,
                type_id=type_id,
            )

            if not deleted:
                raise AdminApartmentTypeNotFoundError(
                    "면적·타입 정보를 삭제하지 못했습니다."
                )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "id": type_id,
            "message": "면적·타입 정보가 삭제되었습니다.",
        }

    @staticmethod
    def list_registration_requests(
        session: Session,
        *,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        items = repository.list_complex_registration_requests(
            session,
            status=status,
            q=q,
            limit=limit,
            offset=offset,
        )
        total = repository.count_complex_registration_requests(
            session,
            status=status,
            q=q,
        )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def complete_registration_request(
        session: Session,
        *,
        request_id: int,
        complex_id: int,
    ) -> dict[str, Any]:
        if repository.find_complex(session, complex_id) is None:
            raise AdminComplexNotFoundError(
                "등록할 단지를 찾을 수 없습니다."
            )

        try:
            updated = repository.complete_complex_registration_request(
                session,
                request_id=request_id,
                complex_id=complex_id,
            )

            if not updated:
                raise ValueError(
                    "등록 요청을 찾을 수 없거나 이미 완료된 요청입니다."
                )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "id": request_id,
            "message": "단지 등록 요청이 완료 처리되었습니다.",
        }
