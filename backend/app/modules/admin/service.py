from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.modules.admin import repository
from app.modules.audit.service import AuditService
from app.modules.event_outbox.service import EventOutboxService


class UserNotFoundError(ValueError):
    pass


class InvalidUserStatusError(ValueError):
    pass


def _suspend_until(suspend_days: int | None) -> datetime | None:
    if suspend_days is None:
        return None
    return datetime.now(timezone.utc) + timedelta(days=suspend_days)


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
        suspend_days: int | None = None,
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

        until = _suspend_until(suspend_days)

        try:
            repository.suspend_company(
                session=session,
                company_id=company_id,
                owner_user_id=company["owner_user_id"],
                reason=reason,
                suspended_until=until,
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
                    "suspended_until": until.isoformat() if until else None,
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
                    "suspended_until": until.isoformat() if until else None,
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
    def unsuspend(
        session: Session,
        *,
        company_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        company = repository.find_company(session, company_id)
        if company is None:
            raise CompanyNotFoundError("업체를 찾을 수 없습니다.")
        if company["status"] != "suspended":
            raise InvalidCompanyStatusError("정지된 업체만 정지 해제할 수 있습니다.")

        try:
            repository.unsuspend_company(session=session, company_id=company_id, owner_user_id=company["owner_user_id"])
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="company.unsuspended",
                target_type="company",
                target_id=company_id,
                before_data={"company_status": "suspended"},
                after_data={"company_status": "active"},
                reason=reason,
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
            "message": "업체 정지가 해제되었습니다.",
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


# 2026-08-26: 일반회원(customer/company 개인 계정) 이용정지 -- 업체 자체를
# 정지하는 AdminCompanyService.suspend와 달리 계정 하나만 정지한다(업체
# 정지는 업체+대표자 계정을 함께 묶어서 처리하는 별개 흐름으로 그대로 둠).
class AdminUserService:
    @staticmethod
    def suspend(
        session: Session,
        *,
        user_id: int,
        admin_user_id: int,
        reason: str,
        suspend_days: int | None = None,
    ) -> dict[str, Any]:
        from app.modules.admin import overview_repository

        user = overview_repository.get_user_detail(session, user_id)
        if user is None:
            raise UserNotFoundError("회원을 찾을 수 없습니다.")
        if user["status"] not in {"active", "pending"}:
            raise InvalidUserStatusError("활성 회원만 정지할 수 있습니다.")

        until = _suspend_until(suspend_days)
        try:
            repository.suspend_user(session=session, user_id=user_id, reason=reason, suspended_until=until)
            repository.revoke_owner_refresh_tokens(session, user_id, "user_suspended")
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="user.suspended",
                target_type="user",
                target_id=user_id,
                before_data={"user_status": user["status"]},
                after_data={"user_status": "suspended", "suspended_until": until.isoformat() if until else None},
                reason=reason,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return {
            "user_id": user_id,
            "user_status": "suspended",
            "suspended_until": until.isoformat() if until else None,
            "message": "회원이 이용정지되었습니다.",
        }

    @staticmethod
    def unsuspend(
        session: Session,
        *,
        user_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        from app.modules.admin import overview_repository

        user = overview_repository.get_user_detail(session, user_id)
        if user is None:
            raise UserNotFoundError("회원을 찾을 수 없습니다.")
        if user["status"] != "suspended":
            raise InvalidUserStatusError("정지된 회원만 정지 해제할 수 있습니다.")

        try:
            repository.unsuspend_user(session=session, user_id=user_id)
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="user.unsuspended",
                target_type="user",
                target_id=user_id,
                before_data={"user_status": "suspended"},
                after_data={"user_status": "active"},
                reason=reason,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return {"user_id": user_id, "user_status": "active", "message": "회원 이용정지가 해제되었습니다."}


def reactivate_expired_suspensions(session: Session) -> dict[str, int]:
    """만료된 이용정지를 자동으로 풀어준다. 시작 시 1회 + 주기적으로 호출됨
    (main.py의 백그라운드 워커에서). 업체는 업체+대표자를 함께 풀고,
    일반회원은 계정만 푼다(업체 대표자는 어차피 회사쪽에서 같이 풀림)."""
    reactivated_companies = 0
    reactivated_users = 0
    try:
        handled_owner_ids: set[int] = set()
        for company in repository.find_expired_suspended_companies(session):
            repository.unsuspend_company(session=session, company_id=company["id"], owner_user_id=company["owner_user_id"])
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.suspension_expired",
                target_type="company",
                target_id=company["id"],
                before_data={"company_status": "suspended"},
                after_data={"company_status": "active"},
                reason="설정된 정지 기간 만료로 자동 해제",
                metadata={"source": "background_worker"},
            )
            handled_owner_ids.add(company["owner_user_id"])
            reactivated_companies += 1

        for user in repository.find_expired_suspended_users(session):
            if user["id"] in handled_owner_ids:
                continue  # 업체 정지 해제에서 이미 같이 풀린 대표자 계정(중복 로그 방지)
            repository.unsuspend_user(session=session, user_id=user["id"])
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="user.suspension_expired",
                target_type="user",
                target_id=user["id"],
                before_data={"user_status": "suspended"},
                after_data={"user_status": "active"},
                reason="설정된 정지 기간 만료로 자동 해제",
                metadata={"source": "background_worker"},
            )
            reactivated_users += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    return {"companies": reactivated_companies, "users": reactivated_users}
