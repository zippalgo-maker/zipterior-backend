import re
import secrets
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.audit.service import AuditService
from app.modules.companies import repository
from app.modules.companies.schemas import CompanyRegisterRequest
from app.modules.event_outbox.service import EventOutboxService


DEFAULT_PLAN_KEY = "launch_partner"


class CompanyEmailAlreadyExistsError(ValueError):
    pass


class CompanyBusinessNumberExistsError(ValueError):
    pass


class CompanyMembershipPlanError(ValueError):
    pass


def make_company_slug(company_name: str) -> str:
    normalized = re.sub(
        r"[^0-9a-zA-Z가-힣]+",
        "-",
        company_name.strip(),
    )
    normalized = normalized.strip("-").lower() or "company"

    return f"{normalized}-{secrets.token_hex(4)}"


class CompanyRegistrationService:
    @staticmethod
    def register(
        session: Session,
        payload: CompanyRegisterRequest,
    ) -> dict[str, Any]:
        if repository.find_user_by_email(session, payload.email):
            raise CompanyEmailAlreadyExistsError(
                "이미 사용 중인 이메일입니다."
            )

        if (
            payload.business_number
            and repository.find_company_by_business_number(
                session,
                payload.business_number,
            )
        ):
            raise CompanyBusinessNumberExistsError(
                "이미 등록된 사업자등록번호입니다."
            )

        plan = repository.get_membership_plan(
            session,
            DEFAULT_PLAN_KEY,
        )

        if plan is None:
            raise CompanyMembershipPlanError(
                "런칭 파트너 회원권을 찾을 수 없습니다."
            )

        try:
            user_id = repository.create_company_user(
                session=session,
                email=payload.email,
                password_hash=hash_password(payload.password),
                name=payload.owner_name or payload.company_name,
                phone=payload.phone,
                marketing_agreed=payload.marketing_agreed,
            )

            company_id = repository.create_company(
                session=session,
                owner_user_id=user_id,
                name=payload.company_name,
                slug=make_company_slug(payload.company_name),
                business_number=payload.business_number,
                representative_name=(
                    payload.representative_name
                    or payload.owner_name
                    or payload.company_name
                ),
                phone=payload.phone,
                email=payload.email,
                postal_code=payload.postal_code,
                address=payload.address,
                address_detail=payload.address_detail,
                sido=payload.sido,
                sigungu=payload.sigungu,
                eupmyeondong=payload.eupmyeondong,
            )

            repository.create_owner_member(
                session=session,
                company_id=company_id,
                user_id=user_id,
            )

            repository.create_onboarding(
                session=session,
                company_id=company_id,
            )

            membership_id = repository.create_membership(
                session=session,
                company_id=company_id,
                plan_id=plan["id"],
                duration_days=plan["duration_days"],
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.self_registered",
                target_type="company",
                target_id=company_id,
                after_data={
                    "user_id": user_id,
                    "company_id": company_id,
                    "membership_id": membership_id,
                    "membership_plan": plan["plan_key"],
                    "user_status": "active",
                    "company_status": "active",
                },
                reason="업체회원 직접 가입",
                metadata={"source": "public_api"},
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyRegistered",
                aggregate_type="company",
                aggregate_id=str(company_id),
                payload={
                    "company_id": company_id,
                    "user_id": user_id,
                    "membership_plan": plan["plan_key"],
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_registration",
                },
            )

            session.commit()

        except IntegrityError as exc:
            session.rollback()
            raise CompanyEmailAlreadyExistsError(
                "이메일 또는 업체 식별정보가 이미 사용 중입니다."
            ) from exc
        except Exception:
            session.rollback()
            raise

        return {
            "user_id": user_id,
            "company_id": company_id,
            "email": payload.email,
            "company_name": payload.company_name,
            "user_status": "active",
            "company_status": "active",
            "membership_plan": plan["plan_key"],
            "message": (
                "업체회원 가입이 완료되었습니다. "
                "바로 로그인하여 서비스를 이용할 수 있습니다."
            ),
        }


from datetime import date, datetime
from decimal import Decimal

from app.modules.companies.schemas import CompanyUpdateRequest


class CompanyAccessDeniedError(ValueError):
    pass


class CompanyNotFoundError(ValueError):
    pass


class EmptyCompanyUpdateError(ValueError):
    pass


class InvalidCompanyUpdateError(ValueError):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


class CompanyMyPageService:
    @staticmethod
    def get_me(
        session: Session,
        *,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        if user["role"] != "company":
            raise CompanyAccessDeniedError(
                "업체회원만 접근할 수 있습니다."
            )

        company = repository.find_company_for_user(
            session,
            user["id"],
        )

        if company is None:
            raise CompanyNotFoundError(
                "연결된 업체정보를 찾을 수 없습니다."
            )

        return company

    @staticmethod
    def update_me(
        session: Session,
        *,
        user: dict[str, Any],
        payload: CompanyUpdateRequest,
    ) -> dict[str, Any]:
        company = CompanyMyPageService.get_me(
            session,
            user=user,
        )

        if company["member_role"] not in {
            "owner",
            "manager",
        }:
            raise CompanyAccessDeniedError(
                "업체 대표 또는 관리자만 수정할 수 있습니다."
            )

        changes = payload.model_dump(
            exclude_unset=True,
        )

        if not changes:
            raise EmptyCompanyUpdateError(
                "수정할 정보가 없습니다."
            )

        if "name" in changes and changes["name"] is None:
            raise InvalidCompanyUpdateError(
                "업체명은 비울 수 없습니다."
            )

        if (
            changes.get("latitude") is not None
            and not -90 <= changes["latitude"] <= 90
        ):
            raise InvalidCompanyUpdateError(
                "위도는 -90부터 90 사이여야 합니다."
            )

        if (
            changes.get("longitude") is not None
            and not -180 <= changes["longitude"] <= 180
        ):
            raise InvalidCompanyUpdateError(
                "경도는 -180부터 180 사이여야 합니다."
            )

        before_data = {
            key: _json_safe(company.get(key))
            for key in changes
        }

        try:
            repository.update_company(
                session=session,
                company_id=company["id"],
                changes=changes,
            )

            updated_company = repository.find_company_for_user(
                session,
                user["id"],
            )

            if updated_company is None:
                raise CompanyNotFoundError(
                    "수정된 업체정보를 조회하지 못했습니다."
                )

            after_data = {
                key: _json_safe(updated_company.get(key))
                for key in changes
            }

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.updated",
                target_type="company",
                target_id=company["id"],
                before_data=before_data,
                after_data=after_data,
                reason="업체회원 업체정보 수정",
                metadata={
                    "source": "company_mypage",
                    "actor_user_id": user["id"],
                    "member_role": company["member_role"],
                    "changed_fields": sorted(changes),
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyUpdated",
                aggregate_type="company",
                aggregate_id=str(company["id"]),
                payload={
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "member_role": company["member_role"],
                    "changed_fields": sorted(changes),
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_mypage",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return updated_company


from app.modules.companies.schemas import CompanyServiceRegionCreateRequest


MAX_SERVICE_REGIONS = 30


class ServiceRegionAlreadyExistsError(ValueError):
    pass


class ServiceRegionLimitError(ValueError):
    pass


class ServiceRegionNotFoundError(ValueError):
    pass


class CompanyServiceRegionService:
    @staticmethod
    def _get_company(
        session: Session,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        return CompanyMyPageService.get_me(
            session=session,
            user=user,
        )

    @staticmethod
    def _require_editor(
        company: dict[str, Any],
    ) -> None:
        if company["member_role"] not in {
            "owner",
            "manager",
        }:
            raise CompanyAccessDeniedError(
                "업체 대표 또는 관리자만 서비스 지역을 변경할 수 있습니다."
            )

    @staticmethod
    def list_regions(
        session: Session,
        *,
        user: dict[str, Any],
    ) -> list[dict[str, Any]]:
        company = CompanyServiceRegionService._get_company(
            session,
            user,
        )

        return repository.list_service_regions(
            session,
            company["id"],
        )

    @staticmethod
    def create_region(
        session: Session,
        *,
        user: dict[str, Any],
        payload: CompanyServiceRegionCreateRequest,
    ) -> dict[str, Any]:
        company = CompanyServiceRegionService._get_company(
            session,
            user,
        )
        CompanyServiceRegionService._require_editor(company)

        existing = repository.find_service_region_by_code(
            session,
            company_id=company["id"],
            region_code=payload.region_code,
        )

        if existing is not None:
            raise ServiceRegionAlreadyExistsError(
                "이미 등록된 서비스 지역입니다."
            )

        current_count = repository.count_service_regions(
            session,
            company["id"],
        )

        if current_count >= MAX_SERVICE_REGIONS:
            raise ServiceRegionLimitError(
                f"서비스 지역은 최대 {MAX_SERVICE_REGIONS}개까지 등록할 수 있습니다."
            )

        is_primary = payload.is_primary or current_count == 0

        try:
            if is_primary:
                repository.clear_primary_service_region(
                    session,
                    company["id"],
                )

            region = repository.create_service_region(
                session=session,
                company_id=company["id"],
                region_code=payload.region_code,
                sido=payload.sido,
                sigungu=payload.sigungu,
                eupmyeondong=payload.eupmyeondong,
                is_primary=is_primary,
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.service_region_created",
                target_type="company_service_region",
                target_id=region["id"],
                after_data={
                    "company_id": company["id"],
                    "region_code": region["region_code"],
                    "sido": region["sido"],
                    "sigungu": region["sigungu"],
                    "eupmyeondong": region["eupmyeondong"],
                    "is_primary": region["is_primary"],
                },
                reason="업체 서비스 지역 등록",
                metadata={
                    "source": "company_mypage",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyServiceRegionCreated",
                aggregate_type="company",
                aggregate_id=str(company["id"]),
                payload={
                    "company_id": company["id"],
                    "region_id": region["id"],
                    "region_code": region["region_code"],
                    "is_primary": region["is_primary"],
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_mypage",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return region

    @staticmethod
    def delete_region(
        session: Session,
        *,
        user: dict[str, Any],
        region_id: int,
    ) -> dict[str, Any]:
        company = CompanyServiceRegionService._get_company(
            session,
            user,
        )
        CompanyServiceRegionService._require_editor(company)

        region = repository.find_service_region_by_id(
            session,
            company_id=company["id"],
            region_id=region_id,
        )

        if region is None:
            raise ServiceRegionNotFoundError(
                "서비스 지역을 찾을 수 없습니다."
            )

        try:
            deleted = repository.delete_service_region(
                session=session,
                company_id=company["id"],
                region_id=region_id,
            )

            if not deleted:
                raise ServiceRegionNotFoundError(
                    "서비스 지역을 삭제하지 못했습니다."
                )

            promoted_region_id = None

            if region["is_primary"]:
                promoted_region_id = (
                    repository.promote_oldest_service_region(
                        session,
                        company["id"],
                    )
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.service_region_deleted",
                target_type="company_service_region",
                target_id=region_id,
                before_data={
                    "company_id": company["id"],
                    "region_code": region["region_code"],
                    "sido": region["sido"],
                    "sigungu": region["sigungu"],
                    "eupmyeondong": region["eupmyeondong"],
                    "is_primary": region["is_primary"],
                },
                after_data={
                    "deleted": True,
                    "promoted_region_id": promoted_region_id,
                },
                reason="업체 서비스 지역 삭제",
                metadata={
                    "source": "company_mypage",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyServiceRegionDeleted",
                aggregate_type="company",
                aggregate_id=str(company["id"]),
                payload={
                    "company_id": company["id"],
                    "region_id": region_id,
                    "region_code": region["region_code"],
                    "promoted_region_id": promoted_region_id,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_mypage",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "region_id": region_id,
            "company_id": company["id"],
            "message": "서비스 지역이 삭제되었습니다.",
        }
