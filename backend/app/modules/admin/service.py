from typing import Any

from sqlalchemy.orm import Session

from app.modules.admin import repository
from app.modules.audit.service import AuditService
from app.modules.event_outbox.service import EventOutboxService


class CompanyNotFoundError(ValueError):
    pass


class InvalidCompanyStatusError(ValueError):
    pass


class AdminCompanyService:
    @staticmethod
    def approve(
        session: Session,
        *,
        company_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        company = repository.find_company(
            session,
            company_id,
        )

        if company is None:
            raise CompanyNotFoundError(
                "업체를 찾을 수 없습니다."
            )

        if company["status"] not in {
            "pending",
            "onboarding",
            "interested",
        }:
            raise InvalidCompanyStatusError(
                "현재 상태에서는 승인할 수 없습니다."
            )

        try:
            repository.approve_company(
                session=session,
                company_id=company_id,
                owner_user_id=company["owner_user_id"],
                admin_user_id=admin_user_id,
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="company.approved",
                target_type="company",
                target_id=company_id,
                before_data={
                    "company_status": company["status"],
                    "user_status": company["owner_status"],
                },
                after_data={
                    "company_status": "active",
                    "user_status": "active",
                },
                reason=reason,
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyApproved",
                aggregate_type="company",
                aggregate_id=str(company_id),
                payload={
                    "company_id": company_id,
                    "owner_user_id": company["owner_user_id"],
                    "approved_by": admin_user_id,
                    "audit_id": audit_id,
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "company_id": company_id,
            "owner_user_id": company["owner_user_id"],
            "company_status": "active",
            "user_status": "active",
            "message": "업체가 승인되었습니다.",
        }

    @staticmethod
    def reject(
        session: Session,
        *,
        company_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        company = repository.find_company(
            session,
            company_id,
        )

        if company is None:
            raise CompanyNotFoundError(
                "업체를 찾을 수 없습니다."
            )

        if company["status"] not in {
            "pending",
            "onboarding",
            "interested",
        }:
            raise InvalidCompanyStatusError(
                "현재 상태에서는 반려할 수 없습니다."
            )

        try:
            repository.reject_company(
                session=session,
                company_id=company_id,
                owner_user_id=company["owner_user_id"],
                reason=reason,
            )

            repository.revoke_owner_refresh_tokens(
                session,
                company["owner_user_id"],
                "company_rejected",
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="company.rejected",
                target_type="company",
                target_id=company_id,
                before_data={
                    "company_status": company["status"],
                    "user_status": company["owner_status"],
                },
                after_data={
                    "company_status": "inactive",
                    "user_status": "withdrawn",
                },
                reason=reason,
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanyRejected",
                aggregate_type="company",
                aggregate_id=str(company_id),
                payload={
                    "company_id": company_id,
                    "owner_user_id": company["owner_user_id"],
                    "rejected_by": admin_user_id,
                    "reason": reason,
                    "audit_id": audit_id,
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "company_id": company_id,
            "owner_user_id": company["owner_user_id"],
            "company_status": "inactive",
            "user_status": "withdrawn",
            "message": "업체 가입 신청이 반려되었습니다.",
        }

    @staticmethod
    def suspend(
        session: Session,
        *,
        company_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        company = repository.find_company(
            session,
            company_id,
        )

        if company is None:
            raise CompanyNotFoundError(
                "업체를 찾을 수 없습니다."
            )

        if company["status"] != "active":
            raise InvalidCompanyStatusError(
                "활성 업체만 정지할 수 있습니다."
            )

        try:
            repository.suspend_company(
                session=session,
                company_id=company_id,
                owner_user_id=company["owner_user_id"],
            )

            repository.revoke_owner_refresh_tokens(
                session,
                company["owner_user_id"],
                "company_suspended",
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="company.suspended",
                target_type="company",
                target_id=company_id,
                before_data={
                    "company_status": company["status"],
                    "user_status": company["owner_status"],
                },
                after_data={
                    "company_status": "suspended",
                    "user_status": "suspended",
                },
                reason=reason,
            )

            EventOutboxService.publish(
                session=session,
                event_name="CompanySuspended",
                aggregate_type="company",
                aggregate_id=str(company_id),
                payload={
                    "company_id": company_id,
                    "owner_user_id": company["owner_user_id"],
                    "suspended_by": admin_user_id,
                    "reason": reason,
                    "audit_id": audit_id,
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "company_id": company_id,
            "owner_user_id": company["owner_user_id"],
            "company_status": "suspended",
            "user_status": "suspended",
            "message": "업체가 정지되었습니다.",
        }

    @staticmethod
    def bulk_status(
        session: Session,
        *,
        company_ids: list[int],
        action: str,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        """2026-08-25: 업체관리 화면 체크박스(개별/전체선택) 일괄 처리용.
        AdminPortfolioService.bulk_status와 동일한 패턴 -- 기존
        approve/reject/suspend를 한 건씩 그대로 재사용해서 검증·감사
        로그·이벤트 발행 로직 중복 없이, 상태 조건이 안 맞는 건만
        개별 실패로 남기고 나머지는 계속 처리한다(부분 성공 허용)."""
        handlers = {
            "approve": AdminCompanyService.approve,
            "reject": AdminCompanyService.reject,
            "suspend": AdminCompanyService.suspend,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"알 수 없는 처리입니다: {action}")

        succeeded: list[int] = []
        failed: list[dict[str, Any]] = []
        for company_id in company_ids:
            try:
                handler(
                    session,
                    company_id=company_id,
                    admin_user_id=admin_user_id,
                    reason=reason,
                )
                succeeded.append(company_id)
            except (CompanyNotFoundError, InvalidCompanyStatusError) as exc:
                failed.append({"company_id": company_id, "error": str(exc)})
        return {"succeeded": succeeded, "failed": failed}
