from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.estimates import repository
from app.modules.estimates.schemas import EstimateCreateRequest
from app.modules.event_outbox.service import EventOutboxService
from app.modules.media.service import ALLOWED_MIME_TYPES, detect_extension
from app.modules.notifications.service import NotificationService


class EstimateNotFoundError(ValueError):
    pass


class EstimateAccessDeniedError(ValueError):
    pass


class EstimateValidationError(ValueError):
    pass


class EstimateStateConflictError(ValueError):
    pass


def _build_estimate(session: Session, row: dict[str, Any], *, include_assignments: bool = False) -> dict[str, Any]:
    data = dict(row)
    data["assignments"] = []
    data["images"] = repository.list_estimate_images(session, estimate_id=row["id"])
    if include_assignments:
        assignments = repository.list_assignments(session, estimate_id=row["id"])
        data["assignments"] = [
            {
                "company": {
                    "id": a["company_id"],
                    "name": a["company_name"],
                    "phone": a["company_phone"],
                    "logo_path": a["company_logo_path"],
                },
                "assignment_order": a["assignment_order"],
                "assignment_score": a["assignment_score"],
                "status": a["status"],
                "assigned_at": a["assigned_at"],
                "viewed_at": a["viewed_at"],
                "responded_at": a["responded_at"],
            }
            for a in assignments
        ]
    return data


def _require_role(user: dict[str, Any], *roles: str) -> None:
    if user.get("role") not in set(roles):
        raise EstimateAccessDeniedError("해당 기능을 사용할 권한이 없습니다.")


ESTIMATE_IMAGE_ROOT = Path("/var/www/zipterior/uploads/estimate-images")
ESTIMATE_IMAGE_URL_PREFIX = "/uploads/estimate-images"
MAX_ESTIMATE_IMAGE_SIZE = 10 * 1024 * 1024
MAX_ESTIMATE_IMAGES = 10


def _remove_managed_estimate_image(file_path: str | None) -> None:
    if not file_path or not file_path.startswith(f"{ESTIMATE_IMAGE_URL_PREFIX}/"):
        return
    filename = file_path.removeprefix(f"{ESTIMATE_IMAGE_URL_PREFIX}/")
    if not filename or "/" in filename or "\\" in filename:
        return
    target = ESTIMATE_IMAGE_ROOT / filename
    if target.exists() and target.is_file():
        target.unlink()


class EstimateService:
    @staticmethod
    def create(session: Session, *, user: dict[str, Any], payload: EstimateCreateRequest) -> dict[str, Any]:
        _require_role(user, "customer")
        refs = repository.validate_references(
            session,
            portfolio_id=payload.portfolio_id,
            complex_id=payload.complex_id,
            apartment_type_id=payload.apartment_type_id,
        )
        if not refs["portfolio"]:
            raise EstimateValidationError("공개된 포트폴리오를 찾을 수 없습니다.")
        if not refs["complex"]:
            raise EstimateValidationError("아파트 단지를 찾을 수 없습니다.")
        if not refs["apartment_type"]:
            raise EstimateValidationError("아파트 평형을 찾을 수 없습니다.")
        if not refs["apartment_type_matches_complex"]:
            raise EstimateValidationError("선택한 평형이 해당 아파트 단지에 속하지 않습니다.")

        try:
            estimate_id = repository.create_estimate(
                session,
                customer_id=user["id"],
                data=payload.model_dump(exclude={"company_ids"}),
            )
            EventOutboxService.publish(
                session=session,
                event_name="EstimateSubmitted",
                aggregate_type="estimate_request",
                aggregate_id=str(estimate_id),
                payload={"estimate_id": estimate_id, "customer_id": user["id"]},
                metadata={"source": "estimate_core"},
            )
            # v2.5.x: 고객이 "같은 조건 시공업체"/"지역 파트너" 후보 중
            # 여러 곳을 직접 골라(company_ids) 한 번에 견적요청을 보내는
            # 다건 배정. 아래 v2.5.1 포트폴리오 단일 자동배정과 동일한
            # 패턴(validate_active_companies + assign_companies)을 그대로
            # 재사용하되, 고객이 명시적으로 고른 대상이라는 점만 다르다.
            # company_ids가 있으면 이걸 우선하고, 없을 때만 기존
            # portfolio_id 기반 단일 자동배정으로 폴백한다(둘 다 없으면
            # 기존처럼 'submitted' 상태로 남아 관리자 배정을 기다림).
            if payload.company_ids:
                active_ids = repository.validate_active_companies(
                    session, company_ids=payload.company_ids
                )
                if active_ids:
                    repository.assign_companies(
                        session, estimate_id=estimate_id, company_ids=active_ids
                    )
                    repository.update_estimate_status(
                        session, estimate_id=estimate_id, status="distributing"
                    )
                    AuditService.record(
                        session=session,
                        admin_user_id=None,
                        action_type="estimate.customer_multi_assigned",
                        target_type="estimate_request",
                        target_id=estimate_id,
                        after_data={"status": "distributing", "company_ids": active_ids},
                        reason="고객이 다건 견적요청 화면에서 직접 선택한 업체 배정",
                        metadata={"source": "customer_multi_select"},
                    )
                    EventOutboxService.publish(
                        session=session,
                        event_name="EstimateAssigned",
                        aggregate_type="estimate_request",
                        aggregate_id=str(estimate_id),
                        payload={"estimate_id": estimate_id, "company_ids": active_ids},
                        metadata={"source": "customer_multi_select"},
                    )
                    NotificationService.notify_companies(
                        session,
                        company_ids=active_ids,
                        notification_type="estimate_assigned",
                        title="새 견적 요청이 배정되었습니다.",
                        message="고객이 여러 업체 중 하나로 선택해 보낸 새로운 견적 요청을 확인해 주세요.",
                        target_type="estimate_request",
                        target_id=estimate_id,
                    )
            # v2.5.1: 포트폴리오에서 들어온 견적문의(portfolio_id 포함)는
            # 관리자가 수동으로 업체를 찾아 배정할 필요 없이, 그 포트폴리오를
            # 등록한 회사로 서버가 스스로 즉시 배정한다(CLAUDE.md 4번 원칙 --
            # "서버가 스스로" 처리 우선). 대상 회사가 이미 비활성/삭제된
            # 경우는 조용히 건너뛰고 기존처럼 관리자 배정 대상('submitted')
            # 으로 남긴다. V2.5.0_PLAN.md 참고. company_ids로 이미 배정됐으면
            # (위 분기) 건너뛴다 -- 같은 견적에 두 경로가 동시에 배정하지
            # 않도록.
            elif payload.portfolio_id is not None:
                company_id = repository.get_portfolio_company_id(
                    session, portfolio_id=payload.portfolio_id
                )
                if company_id is not None and repository.validate_active_companies(
                    session, company_ids=[company_id]
                ):
                    repository.assign_companies(
                        session, estimate_id=estimate_id, company_ids=[company_id]
                    )
                    repository.update_estimate_status(
                        session, estimate_id=estimate_id, status="distributing"
                    )
                    AuditService.record(
                        session=session,
                        admin_user_id=None,
                        action_type="estimate.auto_assigned_by_portfolio",
                        target_type="estimate_request",
                        target_id=estimate_id,
                        after_data={"status": "distributing", "company_ids": [company_id]},
                        reason="포트폴리오 견적문의 CTA를 통한 자동 타겟 배정",
                        metadata={"source": "portfolio_cta", "portfolio_id": payload.portfolio_id},
                    )
                    EventOutboxService.publish(
                        session=session,
                        event_name="EstimateAssigned",
                        aggregate_type="estimate_request",
                        aggregate_id=str(estimate_id),
                        payload={"estimate_id": estimate_id, "company_ids": [company_id]},
                        metadata={"source": "portfolio_cta"},
                    )
                    NotificationService.notify_companies(
                        session,
                        company_ids=[company_id],
                        notification_type="estimate_assigned",
                        title="새 견적 요청이 배정되었습니다.",
                        message="포트폴리오를 보고 들어온 새로운 견적 요청을 확인해 주세요.",
                        target_type="estimate_request",
                        target_id=estimate_id,
                    )
            session.commit()
        except Exception:
            session.rollback()
            raise

        row = repository.find_customer_estimate(session, estimate_id=estimate_id, customer_id=user["id"])
        return _build_estimate(session, row)

    @staticmethod
    def list_mine(session: Session, *, user: dict[str, Any], limit: int, offset: int) -> dict[str, Any]:
        _require_role(user, "customer")
        rows = repository.list_customer_estimates(session, customer_id=user["id"], limit=limit, offset=offset)
        return {
            "items": [_build_estimate(session, row) for row in rows],
            "total": repository.count_customer_estimates(session, customer_id=user["id"]),
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def get_mine(session: Session, *, user: dict[str, Any], estimate_id: int) -> dict[str, Any]:
        _require_role(user, "customer")
        row = repository.find_customer_estimate(session, estimate_id=estimate_id, customer_id=user["id"])
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        return _build_estimate(session, row, include_assignments=True)

    @staticmethod
    def cancel(session: Session, *, user: dict[str, Any], estimate_id: int) -> dict[str, Any]:
        _require_role(user, "customer")
        row = repository.find_customer_estimate(session, estimate_id=estimate_id, customer_id=user["id"])
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] in {"contracted", "closed", "cancelled"}:
            raise EstimateStateConflictError("현재 상태에서는 견적 요청을 취소할 수 없습니다.")
        try:
            repository.update_estimate_status(session, estimate_id=estimate_id, status="cancelled")
            EventOutboxService.publish(
                session=session,
                event_name="EstimateCancelled",
                aggregate_type="estimate_request",
                aggregate_id=str(estimate_id),
                payload={"estimate_id": estimate_id, "customer_id": user["id"]},
                metadata={"source": "estimate_core"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"estimate_id": estimate_id, "status": "cancelled", "message": "견적 요청이 취소되었습니다."}

    @staticmethod
    def _company(session: Session, user: dict[str, Any]) -> dict[str, Any]:
        _require_role(user, "company")
        company = repository.find_company_for_user(session, user_id=user["id"])
        if company is None or company["status"] != "active":
            raise EstimateAccessDeniedError("활성 회원사 정보를 찾을 수 없습니다.")
        return company

    @staticmethod
    def list_company(session: Session, *, user: dict[str, Any], assignment_status: str | None, limit: int, offset: int) -> dict[str, Any]:
        company = EstimateService._company(session, user)
        rows = repository.list_company_estimates(session, company_id=company["id"], assignment_status=assignment_status, limit=limit, offset=offset)
        items = []
        for row in rows:
            detail = repository.get_company_estimate(session, estimate_id=row["id"], company_id=company["id"])
            detail["assignments"] = []
            items.append(detail)
        return {
            "items": items,
            "total": repository.count_company_estimates(session, company_id=company["id"], assignment_status=assignment_status),
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def company_insights(session: Session, *, user: dict[str, Any]) -> dict[str, Any]:
        """v2.5.41(2026-08-23) UX 도면 F9 -- 업체 대시보드 홈에 "지난주
        대비" 비교 지표와 "견적을 놓친 이유" 힌트를 보여주기 위한 집계.
        관리자 개입 없이 서버가 스스로 계산해서 보여준다(CLAUDE.md 0번
        전자동화 원칙과 같은 방향)."""
        company = EstimateService._company(session, user)
        company_id = company["id"]
        this_week = repository.company_insights_window(session, company_id=company_id, days_ago_start=7, days_ago_end=0)
        last_week = repository.company_insights_window(session, company_id=company_id, days_ago_start=14, days_ago_end=7)
        pending_over_24h = repository.company_pending_over_24h(session, company_id=company_id)
        avg_images = repository.company_avg_portfolio_images(session, company_id=company_id)

        hints: list[str] = []
        if pending_over_24h > 0:
            hints.append(f"응답 대기 중인 견적이 {pending_over_24h}건 있습니다. 24시간 안에 응답하면 계약 전환율이 올라갑니다.")
        if this_week["declined_count"] and this_week["avg_response_hours"] and this_week["avg_response_hours"] > 24:
            hours = round(this_week["avg_response_hours"])
            hints.append(f"이번 주 놓친 견적 {this_week['declined_count']}건의 평균 응답 시간이 {hours}시간이었습니다 -- 더 빠르게 응답해 보세요.")
        if avg_images is None:
            hints.append("승인된 포트폴리오가 아직 없습니다. 포트폴리오를 등록하면 고객에게 노출됩니다.")
        elif avg_images < 8:
            hints.append(f"등록한 포트폴리오의 평균 사진 수가 {avg_images:.1f}장으로 적은 편입니다 -- 사진이 많을수록 노출과 문의가 늘어납니다.")
        if this_week["assigned_count"] < last_week["assigned_count"]:
            hints.append("이번 주 배정된 견적이 지난주보다 줄었습니다 -- 업체정보·포트폴리오가 최신 상태인지 확인해 보세요.")

        return {
            "this_week": this_week,
            "last_week": last_week,
            "pending_over_24h": pending_over_24h,
            "avg_portfolio_images": avg_images,
            "hints": hints,
        }

    @staticmethod
    def get_company(session: Session, *, user: dict[str, Any], estimate_id: int) -> dict[str, Any]:
        company = EstimateService._company(session, user)
        row = repository.get_company_estimate(session, estimate_id=estimate_id, company_id=company["id"])
        if row is None:
            raise EstimateNotFoundError("배정된 견적 요청을 찾을 수 없습니다.")
        row["assignments"] = []
        return row

    @staticmethod
    def company_action(session: Session, *, user: dict[str, Any], estimate_id: int, action: str) -> dict[str, Any]:
        company = EstimateService._company(session, user)
        assignment = repository.find_company_assignment(session, estimate_id=estimate_id, company_id=company["id"])
        if assignment is None:
            raise EstimateNotFoundError("배정된 견적 요청을 찾을 수 없습니다.")
        if assignment["estimate_status"] in {"closed", "cancelled"}:
            raise EstimateStateConflictError("종료된 견적 요청입니다.")

        allowed = {
            "view": ({"unread"}, "viewed", "EstimateViewed", "견적 요청을 확인했습니다."),
            "respond": ({"unread", "viewed"}, "responded", "EstimateResponded", "견적 요청에 응답했습니다."),
            "decline": ({"unread", "viewed", "responded"}, "declined", "EstimateDeclined", "견적 요청을 거절했습니다."),
            "contract": ({"unread", "viewed", "responded"}, "contracted", "EstimateContracted", "계약 처리되었습니다."),
        }
        valid_from, next_status, event_name, message = allowed[action]
        if assignment["status"] == next_status:
            estimate_status = "contracted" if action == "contract" else assignment["estimate_status"]
            return {"estimate_id": estimate_id, "company_id": company["id"], "assignment_status": next_status, "estimate_status": estimate_status, "message": message}
        if assignment["status"] not in valid_from:
            raise EstimateStateConflictError("현재 상태에서는 해당 처리를 할 수 없습니다.")

        try:
            repository.update_assignment_status(session, estimate_id=estimate_id, company_id=company["id"], status=next_status)
            estimate_status = assignment["estimate_status"]
            if action == "respond" and estimate_status in {"submitted", "distributing"}:
                repository.update_estimate_status(session, estimate_id=estimate_id, status="consulting")
                estimate_status = "consulting"
            if action == "contract":
                repository.update_estimate_status(session, estimate_id=estimate_id, status="contracted")
                repository.expire_other_assignments(session, estimate_id=estimate_id, contracted_company_id=company["id"])
                estimate_status = "contracted"
            EventOutboxService.publish(
                session=session,
                event_name=event_name,
                aggregate_type="estimate_request",
                aggregate_id=str(estimate_id),
                payload={"estimate_id": estimate_id, "company_id": company["id"], "assignment_status": next_status, "estimate_status": estimate_status},
                metadata={"source": "estimate_core"},
            )
            estimate_row = repository.find_estimate(session, estimate_id=estimate_id)
            if estimate_row and action in {"respond", "decline", "contract"}:
                NotificationService.create(
                    session, user_id=estimate_row["customer_id"],
                    notification_type=f"estimate_{action}",
                    title={
                        "respond": "업체가 견적 요청에 응답했습니다.",
                        "decline": "업체가 견적 요청을 거절했습니다.",
                        "contract": "견적 요청이 계약 처리되었습니다.",
                    }[action],
                    message=f"{company['name']} 업체의 처리 내역을 확인해 주세요.",
                    target_type="estimate_request", target_id=estimate_id,
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"estimate_id": estimate_id, "company_id": company["id"], "assignment_status": next_status, "estimate_status": estimate_status, "message": message}

    @staticmethod
    def list_admin(session: Session, *, estimate_status: str | None, limit: int, offset: int) -> dict[str, Any]:
        rows = repository.list_admin_estimates(session, estimate_status=estimate_status, limit=limit, offset=offset)
        return {
            "items": [_build_estimate(session, row) for row in rows],
            "total": repository.count_admin_estimates(session, estimate_status=estimate_status),
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def get_admin(session: Session, *, estimate_id: int) -> dict[str, Any]:
        row = repository.find_estimate(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        return _build_estimate(session, row, include_assignments=True)

    @staticmethod
    def assign_admin(session: Session, *, admin_user_id: int, estimate_id: int, company_ids: list[int]) -> dict[str, Any]:
        row = repository.find_estimate(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] in {"contracted", "closed", "cancelled"}:
            raise EstimateStateConflictError("현재 상태에서는 업체를 배정할 수 없습니다.")
        valid = repository.validate_active_companies(session, company_ids=company_ids)
        invalid = sorted(set(company_ids) - set(valid))
        if invalid:
            raise EstimateValidationError(f"활성 상태가 아닌 업체가 포함되어 있습니다: {invalid}")
        try:
            repository.assign_companies(session, estimate_id=estimate_id, company_ids=company_ids)
            repository.update_estimate_status(session, estimate_id=estimate_id, status="distributing")
            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="estimate.assigned",
                target_type="estimate_request",
                target_id=estimate_id,
                before_data={"status": row["status"]},
                after_data={"status": "distributing", "company_ids": company_ids},
                reason="견적 요청 업체 배정",
                metadata={"source": "estimate_core"},
            )
            EventOutboxService.publish(
                session=session,
                event_name="EstimateAssigned",
                aggregate_type="estimate_request",
                aggregate_id=str(estimate_id),
                payload={"estimate_id": estimate_id, "company_ids": company_ids, "admin_user_id": admin_user_id, "audit_id": audit_id},
                metadata={"source": "estimate_core"},
            )
            NotificationService.notify_companies(
                session, company_ids=company_ids, notification_type="estimate_assigned",
                title="새 견적 요청이 배정되었습니다.",
                message="새로운 견적 요청을 확인해 주세요.", target_type="estimate_request", target_id=estimate_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"estimate_id": estimate_id, "status": "distributing", "assigned_company_ids": company_ids, "assignment_count": len(repository.list_assignments(session, estimate_id=estimate_id)), "message": "견적 요청 업체 배정이 완료되었습니다."}

    @staticmethod
    def set_admin_status(session: Session, *, admin_user_id: int, estimate_id: int, status: str, reason: str | None) -> dict[str, Any]:
        row = repository.find_estimate(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] == status:
            return {"estimate_id": estimate_id, "status": status, "message": "이미 해당 상태입니다."}
        try:
            repository.update_estimate_status(session, estimate_id=estimate_id, status=status)
            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="estimate.status_changed",
                target_type="estimate_request",
                target_id=estimate_id,
                before_data={"status": row["status"]},
                after_data={"status": status},
                reason=reason or "견적 요청 상태 변경",
                metadata={"source": "estimate_core"},
            )
            EventOutboxService.publish(
                session=session,
                event_name="EstimateStatusChanged",
                aggregate_type="estimate_request",
                aggregate_id=str(estimate_id),
                payload={"estimate_id": estimate_id, "status": status, "admin_user_id": admin_user_id, "audit_id": audit_id},
                metadata={"source": "estimate_core"},
            )
            NotificationService.create(
                session, user_id=row["customer_id"], notification_type="estimate_status_changed",
                title="견적 요청 상태가 변경되었습니다.",
                message=f"견적 요청 상태: {status}", target_type="estimate_request", target_id=estimate_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"estimate_id": estimate_id, "status": status, "message": "견적 요청 상태가 변경되었습니다."}


    @staticmethod
    async def upload_image(session: Session, *, user: dict[str, Any], estimate_id: int, upload: UploadFile) -> dict[str, Any]:
        _require_role(user, "customer")
        row = repository.find_customer_estimate(session, estimate_id=estimate_id, customer_id=user["id"])
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] in {"contracted", "closed", "cancelled"}:
            raise EstimateStateConflictError("현재 상태에서는 이미지를 변경할 수 없습니다.")
        if repository.count_estimate_images(session, estimate_id=estimate_id) >= MAX_ESTIMATE_IMAGES:
            raise EstimateValidationError(f"견적 이미지는 최대 {MAX_ESTIMATE_IMAGES}장까지 등록할 수 있습니다.")
        if upload.content_type not in ALLOWED_MIME_TYPES:
            raise EstimateValidationError("JPG, PNG, WEBP 이미지만 업로드할 수 있습니다.")
        data = await upload.read(MAX_ESTIMATE_IMAGE_SIZE + 1)
        if not data:
            raise EstimateValidationError("비어 있는 파일은 업로드할 수 없습니다.")
        if len(data) > MAX_ESTIMATE_IMAGE_SIZE:
            raise EstimateValidationError("견적 이미지는 한 장당 최대 10MB까지 업로드할 수 있습니다.")
        detected = detect_extension(data)
        if detected is None or detected != ALLOWED_MIME_TYPES[upload.content_type]:
            raise EstimateValidationError("파일 내용과 이미지 형식이 일치하지 않습니다.")
        ESTIMATE_IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
        filename = f"estimate_{estimate_id}_{uuid4().hex}{detected}"
        target = ESTIMATE_IMAGE_ROOT / filename
        file_path = f"{ESTIMATE_IMAGE_URL_PREFIX}/{filename}"
        try:
            target.write_bytes(data)
            image = repository.create_estimate_image(session, estimate_id=estimate_id, file_path=file_path)
            EventOutboxService.publish(
                session=session, event_name="EstimateImageAdded", aggregate_type="estimate_request",
                aggregate_id=str(estimate_id), payload={"estimate_id": estimate_id, "image_id": image["id"], "user_id": user["id"]},
                metadata={"source": "estimate_attachment"},
            )
            session.commit()
        except Exception:
            session.rollback()
            if target.exists():
                target.unlink()
            raise
        return {"estimate_id": estimate_id, "image": image, "image_count": repository.count_estimate_images(session, estimate_id=estimate_id), "message": "견적 이미지가 등록되었습니다."}

    @staticmethod
    def delete_image(session: Session, *, user: dict[str, Any], estimate_id: int, image_id: int) -> dict[str, Any]:
        _require_role(user, "customer")
        row = repository.find_customer_estimate(session, estimate_id=estimate_id, customer_id=user["id"])
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] in {"contracted", "closed", "cancelled"}:
            raise EstimateStateConflictError("현재 상태에서는 이미지를 변경할 수 없습니다.")
        image = repository.find_estimate_image(session, estimate_id=estimate_id, image_id=image_id)
        if image is None:
            raise EstimateNotFoundError("견적 이미지를 찾을 수 없습니다.")
        try:
            repository.delete_estimate_image(session, estimate_id=estimate_id, image_id=image_id)
            EventOutboxService.publish(
                session=session, event_name="EstimateImageDeleted", aggregate_type="estimate_request",
                aggregate_id=str(estimate_id), payload={"estimate_id": estimate_id, "image_id": image_id, "user_id": user["id"]},
                metadata={"source": "estimate_attachment"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        _remove_managed_estimate_image(image["file_path"])
        return {"estimate_id": estimate_id, "image_id": image_id, "image_count": repository.count_estimate_images(session, estimate_id=estimate_id), "message": "견적 이미지가 삭제되었습니다."}

    @staticmethod
    def auto_assign_admin(session: Session, *, admin_user_id: int, estimate_id: int, limit: int) -> dict[str, Any]:
        row = repository.find_estimate(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if row["status"] in {"contracted", "closed", "cancelled"}:
            raise EstimateStateConflictError("현재 상태에서는 자동 배정할 수 없습니다.")
        if not row["allow_recommendations"]:
            raise EstimateStateConflictError("고객이 업체 추천을 허용하지 않은 견적입니다.")
        candidates = repository.list_auto_assignment_candidates(session, estimate_id=estimate_id, limit=limit)
        if not candidates:
            raise EstimateValidationError("자동 배정 가능한 업체가 없습니다.")
        company_ids = [int(c["company_id"]) for c in candidates]
        try:
            repository.assign_scored_companies(session, estimate_id=estimate_id, candidates=candidates)
            repository.update_estimate_status(session, estimate_id=estimate_id, status="distributing")
            audit_id = AuditService.record(
                session=session, admin_user_id=admin_user_id, action_type="estimate.auto_assigned",
                target_type="estimate_request", target_id=estimate_id,
                before_data={"status": row["status"]},
                after_data={"status": "distributing", "company_ids": company_ids, "limit": limit},
                reason="견적 요청 자동 추천/배정", metadata={"source": "estimate_distribution_v1"},
            )
            EventOutboxService.publish(
                session=session, event_name="EstimateAutoAssigned", aggregate_type="estimate_request",
                aggregate_id=str(estimate_id), payload={"estimate_id": estimate_id, "company_ids": company_ids, "admin_user_id": admin_user_id, "audit_id": audit_id},
                metadata={"source": "estimate_distribution_v1"},
            )
            NotificationService.notify_companies(
                session, company_ids=company_ids, notification_type="estimate_assigned",
                title="추천 견적 요청이 배정되었습니다.", message="자동 추천된 신규 견적 요청을 확인해 주세요.",
                target_type="estimate_request", target_id=estimate_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {
            "estimate_id": estimate_id, "status": "distributing", "assigned_company_ids": company_ids,
            "assignment_count": len(repository.list_assignments(session, estimate_id=estimate_id)),
            "candidate_count": len(candidates), "message": "견적 요청 자동 추천/배정이 완료되었습니다.",
        }

    # v1.10.1(2026-08-26): 시공 진행상황(목업 13번 화면). 새 테이블
    # estimate_milestones만 추가하고 댓글은 기존 chat 모듈(estimate_
    # request_id로 연결된 고객-업체 상담방)을 그대로 재사용한다 -- 별도
    # 댓글 API 불필요.
    @staticmethod
    def _check_milestone_access(session: Session, *, user: dict[str, Any], row: dict[str, Any]) -> None:
        if user["role"] == "customer":
            if row["customer_id"] != user["id"]:
                raise EstimateAccessDeniedError("본인 견적 요청만 조회할 수 있습니다.")
        elif user["role"] == "company":
            company = EstimateService._company(session, user)
            assignment = repository.find_company_assignment(session, estimate_id=row["id"], company_id=company["id"])
            if assignment is None:
                raise EstimateAccessDeniedError("배정된 견적 요청이 아닙니다.")
        elif user["role"] not in {"admin", "super_admin"}:
            raise EstimateAccessDeniedError("해당 기능을 사용할 권한이 없습니다.")

    @staticmethod
    def get_milestones(session: Session, *, user: dict[str, Any], estimate_id: int) -> dict[str, Any]:
        row = repository.find_estimate_by_id(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        EstimateService._check_milestone_access(session, user=user, row=row)

        items = repository.list_milestones(session, estimate_id=estimate_id)
        if not items and row["status"] in {"contracted", "closed"}:
            repository.seed_milestones(session, estimate_id=estimate_id, all_done=row["status"] == "closed")
            items = repository.list_milestones(session, estimate_id=estimate_id)
        return {"items": items}

    @staticmethod
    def update_milestone(session: Session, *, user: dict[str, Any], estimate_id: int, phase_key: str, status: str, note: str | None) -> dict[str, Any]:
        row = repository.find_estimate_by_id(session, estimate_id=estimate_id)
        if row is None:
            raise EstimateNotFoundError("견적 요청을 찾을 수 없습니다.")
        if user["role"] == "company":
            company = EstimateService._company(session, user)
            assignment = repository.find_company_assignment(session, estimate_id=estimate_id, company_id=company["id"])
            if assignment is None or assignment["status"] != "contracted":
                raise EstimateAccessDeniedError("계약된 견적 요청만 진행상황을 업데이트할 수 있습니다.")
        elif user["role"] not in {"admin", "super_admin"}:
            raise EstimateAccessDeniedError("해당 기능을 사용할 권한이 없습니다.")
        if row["status"] not in {"contracted", "closed"}:
            raise EstimateStateConflictError("계약 이후에만 진행상황을 기록할 수 있습니다.")

        if not repository.list_milestones(session, estimate_id=estimate_id):
            repository.seed_milestones(session, estimate_id=estimate_id, all_done=False)
        repository.upsert_milestone(session, estimate_id=estimate_id, phase_key=phase_key, status=status, note=note)

        prefs = session.execute(
            text("SELECT notification_prefs FROM users WHERE id=:id"), {"id": row["customer_id"]}
        ).scalar()
        if (prefs or {}).get("photo_upload", True):
            NotificationService.create(
                session, user_id=row["customer_id"], notification_type="milestone_updated",
                title="시공 진행상황이 업데이트됐어요", message=f"{row.get('complex_name') or '견적'} 공정 소식이 도착했어요.",
                target_type="estimate_request", target_id=estimate_id,
            )
        session.commit()
        return {"items": repository.list_milestones(session, estimate_id=estimate_id)}
