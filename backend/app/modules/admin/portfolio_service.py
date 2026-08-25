from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.modules.admin import portfolio_repository as repository
from app.modules.audit.service import AuditService
from app.modules.bulk_import import repository as bulk_import_repository
from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios.image_service import CompanyPortfolioImageService
from app.modules.portfolios.schemas import PortfolioImageUpdateRequest


class AdminPortfolioNotFoundError(ValueError):
    pass


class InvalidPortfolioStatusError(ValueError):
    pass


def _admin_image_user(admin_user_id: int, company_id: int) -> dict[str, Any]:
    # 이미지 편집 서비스(CompanyPortfolioImageService)가 이미 알고 있는
    # 관리자 대리 컨텍스트(_bulk_import_company_id + super_admin)를 그대로
    # 쓰되, 승인·공개 상태에서도 편집 가능하도록 _admin_edit_bypass_status를
    # 추가로 켠다(image_service.py의 _get_editable_context 참고).
    return {
        "id": admin_user_id,
        "role": "super_admin",
        "_bulk_import_company_id": company_id,
        "_admin_edit_bypass_status": True,
    }


class AdminPortfolioService:
    @staticmethod
    def list_pending(
        session: Session,
    ) -> list[dict[str, Any]]:
        return repository.list_pending_portfolios(session)

    @staticmethod
    def list_portfolios(
        session: Session,
        *,
        q: str | None,
        status_filter: str | None,
        needs_review: bool | None = None,
        review_reason_contains: str | None = None,
        construction_scope_filter: str | None = None,
        created_date: str | None = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        items = repository.list_portfolios(
            session,
            q=q,
            status_filter=status_filter,
            needs_review=needs_review,
            review_reason_contains=review_reason_contains,
            construction_scope_filter=construction_scope_filter,
            created_date=created_date,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        # v2.5.0 (테스트, additive): 원문 재현 테스트 대상인지 표시만 한다 --
        # 기존 목록 쿼리는 손대지 않고 배치로 한 번 더 조회해 덧붙인다.
        with_blocks = bulk_import_repository.has_content_blocks(
            session, portfolio_ids=[item["id"] for item in items]
        )
        for item in items:
            item["has_content_blocks"] = item["id"] in with_blocks
        total = repository.count_portfolios(
            session,
            q=q,
            status_filter=status_filter,
            needs_review=needs_review,
            review_reason_contains=review_reason_contains,
            construction_scope_filter=construction_scope_filter,
            created_date=created_date,
        )
        return {"items": items, "total": total}

    @staticmethod
    def get_detail(
        session: Session,
        portfolio_id: int,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        # v2.5.0 (원문 재현): 있으면 관리자 "집테리어 보기" 미리보기도
        # 원문 순서 그대로 보여준다 -- 없으면 빈 배열, 프론트가 기존
        # 공간별 미리보기로 자동 대체(에러 아님).
        detail["content_blocks"] = bulk_import_repository.list_content_blocks(
            session, portfolio_id=portfolio_id
        )
        return detail

    @staticmethod
    def update_text(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        title: str | None,
        summary: str | None,
        description: str | None,
    ) -> dict[str, Any]:
        before = repository.find_portfolio_detail(session, portfolio_id)
        if before is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = repository.update_portfolio_text(
                session,
                portfolio_id=portfolio_id,
                title=title,
                summary=summary,
                description=description,
            )
            if result is None:
                raise AdminPortfolioNotFoundError(
                    "포트폴리오를 찾을 수 없습니다."
                )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.text_edited",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "title": before["title"],
                    "summary": before["summary"],
                    "description": before["description"],
                },
                after_data=result,
                reason="관리자 원본 대조 수정",
                metadata={"source": "admin_portfolio_compare"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def assign_complex(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        complex_id: int,
        apartment_type_id: int | None,
    ) -> dict[str, Any]:
        """v2.5.0: 대량등록에서 단지를 못 찾아 'draft'+review_reason으로 남은
        포트폴리오에 관리자가 직접 단지를 지정한다. review_reason이 있던
        건이면 그 자리에서 'approved'로 전환된다(repository 참고) -- 지도
        마커가 뜨는 것까지가 이 액션의 목적이다."""
        before = repository.find_portfolio_detail(session, portfolio_id)
        if before is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = repository.assign_portfolio_complex(
                session,
                portfolio_id=portfolio_id,
                complex_id=complex_id,
                apartment_type_id=apartment_type_id,
            )
            if result is None:
                raise AdminPortfolioNotFoundError(
                    "포트폴리오를 찾을 수 없습니다."
                )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.complex_assigned",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "complex_id": before["complex_id"],
                    "status": before["status"],
                    "review_reason": before["review_reason"],
                },
                after_data=result,
                reason="관리자 확인필요 포트폴리오 단지 지정",
                metadata={"source": "admin_portfolio_needs_review"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def update_space_text(
        session: Session,
        *,
        portfolio_id: int,
        space_id: int,
        admin_user_id: int,
        description: str | None,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        before_space = next(
            (s for s in detail["spaces"] if s["id"] == space_id), None
        )
        if before_space is None:
            raise AdminPortfolioNotFoundError(
                "공간을 찾을 수 없습니다."
            )
        try:
            result = repository.update_space_text(
                session,
                portfolio_id=portfolio_id,
                space_id=space_id,
                description=description,
            )
            if result is None:
                raise AdminPortfolioNotFoundError(
                    "공간을 찾을 수 없습니다."
                )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.space_text_edited",
                target_type="portfolio_space",
                target_id=space_id,
                before_data={"description": before_space["description"]},
                after_data=result,
                reason="관리자 원본 대조 수정",
                metadata={
                    "source": "admin_portfolio_compare",
                    "portfolio_id": portfolio_id,
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def reorder_spaces(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        space_ids: list[int],
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        before_order = [s["id"] for s in detail["spaces"]]
        try:
            updated = repository.reorder_spaces(
                session,
                portfolio_id=portfolio_id,
                space_ids=space_ids,
            )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.spaces_reordered",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={"space_order": before_order},
                after_data={"space_order": space_ids},
                reason="관리자 원본 대조 수정",
                metadata={"source": "admin_portfolio_compare"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"portfolio_id": portfolio_id, "updated": updated}

    @staticmethod
    def approve(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        portfolio = repository.find_portfolio(
            session,
            portfolio_id,
        )

        if portfolio is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] != "pending":
            raise InvalidPortfolioStatusError(
                "승인 대기 상태의 포트폴리오만 승인할 수 있습니다."
            )

        try:
            result = repository.approve_portfolio(
                session,
                portfolio_id=portfolio_id,
            )

            if result is None:
                raise InvalidPortfolioStatusError(
                    "포트폴리오 승인 상태를 변경하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.approved",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "status": portfolio["status"],
                    "published_at": (
                        portfolio["published_at"].isoformat()
                        if portfolio["published_at"]
                        else None
                    ),
                },
                after_data={
                    "status": result["status"],
                    "published_at": (
                        result["published_at"].isoformat()
                        if result["published_at"]
                        else None
                    ),
                },
                reason=reason,
                metadata={
                    "source": "admin_portfolio",
                    "company_id": result["company_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioApproved",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": result["company_id"],
                    "admin_user_id": admin_user_id,
                    "published_at": (
                        result["published_at"].isoformat()
                        if result["published_at"]
                        else None
                    ),
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "admin_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            **result,
            "message": "포트폴리오가 승인되었습니다.",
        }

    @staticmethod
    def reject(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        portfolio = repository.find_portfolio(
            session,
            portfolio_id,
        )

        if portfolio is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] != "pending":
            raise InvalidPortfolioStatusError(
                "승인 대기 상태의 포트폴리오만 반려할 수 있습니다."
            )

        try:
            result = repository.reject_portfolio(
                session,
                portfolio_id=portfolio_id,
                reason=reason,
            )

            if result is None:
                raise InvalidPortfolioStatusError(
                    "포트폴리오 반려 상태를 변경하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.rejected",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "status": portfolio["status"],
                    "rejection_reason": (
                        portfolio["rejection_reason"]
                    ),
                },
                after_data={
                    "status": result["status"],
                    "rejection_reason": (
                        result["rejection_reason"]
                    ),
                },
                reason=reason,
                metadata={
                    "source": "admin_portfolio",
                    "company_id": result["company_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioRejected",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": result["company_id"],
                    "admin_user_id": admin_user_id,
                    "reason": reason,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "admin_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            **result,
            "message": "포트폴리오가 반려되었습니다.",
        }

    @staticmethod
    def hide(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        portfolio = repository.find_portfolio(
            session,
            portfolio_id,
        )

        if portfolio is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] != "approved":
            raise InvalidPortfolioStatusError(
                "승인된 포트폴리오만 숨김 처리할 수 있습니다."
            )

        try:
            result = repository.hide_portfolio(
                session,
                portfolio_id=portfolio_id,
            )

            if result is None:
                raise InvalidPortfolioStatusError(
                    "포트폴리오 숨김 상태를 변경하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.hidden",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "status": portfolio["status"],
                },
                after_data={
                    "status": result["status"],
                },
                reason=reason,
                metadata={
                    "source": "admin_portfolio",
                    "company_id": result["company_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioHidden",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": result["company_id"],
                    "admin_user_id": admin_user_id,
                    "reason": reason,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "admin_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            **result,
            "message": "포트폴리오가 숨김 처리되었습니다.",
        }

    @staticmethod
    def unhide(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        portfolio = repository.find_portfolio(
            session,
            portfolio_id,
        )

        if portfolio is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] != "hidden":
            raise InvalidPortfolioStatusError(
                "숨김 상태의 포트폴리오만 숨김 해제할 수 있습니다."
            )

        try:
            result = repository.unhide_portfolio(
                session,
                portfolio_id=portfolio_id,
            )

            if result is None:
                raise InvalidPortfolioStatusError(
                    "포트폴리오 숨김 상태를 변경하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.unhidden",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "status": portfolio["status"],
                },
                after_data={
                    "status": result["status"],
                },
                reason=reason,
                metadata={
                    "source": "admin_portfolio",
                    "company_id": result["company_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioUnhidden",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": result["company_id"],
                    "admin_user_id": admin_user_id,
                    "reason": reason,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "admin_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            **result,
            "message": "포트폴리오 숨김이 해제되어 다시 공개됩니다.",
        }

    @staticmethod
    def bulk_status(
        session: Session,
        *,
        portfolio_ids: list[int],
        action: str,
        admin_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        """v2.5.0: 포트폴리오 관리 화면 체크박스(개별/전체선택) 일괄 처리용.
        기존 approve/reject/hide/unhide를 그대로 한 건씩 재사용한다(검증·감사
        로그·이벤트 발행 로직 중복 없음) -- 한 건이 상태 조건에 안 맞아
        실패해도 나머지는 계속 처리하고, 성공/실패 목록을 모두 돌려준다."""
        handlers = {
            "approve": AdminPortfolioService.approve,
            "reject": AdminPortfolioService.reject,
            "hide": AdminPortfolioService.hide,
            "unhide": AdminPortfolioService.unhide,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"알 수 없는 처리입니다: {action}")

        succeeded: list[int] = []
        failed: list[dict[str, Any]] = []
        for portfolio_id in portfolio_ids:
            try:
                handler(
                    session,
                    portfolio_id=portfolio_id,
                    admin_user_id=admin_user_id,
                    reason=reason,
                )
                succeeded.append(portfolio_id)
            except (AdminPortfolioNotFoundError, InvalidPortfolioStatusError) as exc:
                failed.append({"portfolio_id": portfolio_id, "error": str(exc)})
        return {"succeeded": succeeded, "failed": failed}

    @staticmethod
    async def upload_image(
        session: Session,
        *,
        portfolio_id: int,
        admin_user_id: int,
        room_code: str,
        portfolio_space_id: int | None,
        upload: UploadFile,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = await CompanyPortfolioImageService.upload_image(
                session,
                user=_admin_image_user(
                    admin_user_id, detail["company_id"]
                ),
                portfolio_id=portfolio_id,
                room_code=room_code,
                portfolio_space_id=portfolio_space_id,
                upload=upload,
            )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.image_added",
                target_type="portfolio_image",
                target_id=result["id"],
                after_data={"portfolio_id": portfolio_id, "room_code": room_code},
                reason="관리자 원본 대조 수정",
                metadata={"source": "admin_portfolio_compare"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def update_image(
        session: Session,
        *,
        portfolio_id: int,
        image_id: int,
        admin_user_id: int,
        sort_order: int | None,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = CompanyPortfolioImageService.update_image(
                session,
                user=_admin_image_user(
                    admin_user_id, detail["company_id"]
                ),
                portfolio_id=portfolio_id,
                image_id=image_id,
                payload=PortfolioImageUpdateRequest(sort_order=sort_order),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def move_image_to_space(
        session: Session,
        *,
        portfolio_id: int,
        image_id: int,
        admin_user_id: int,
        portfolio_space_id: int,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = CompanyPortfolioImageService.move_image_to_space(
                session,
                user=_admin_image_user(
                    admin_user_id, detail["company_id"]
                ),
                portfolio_id=portfolio_id,
                image_id=image_id,
                portfolio_space_id=portfolio_space_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result

    @staticmethod
    def delete_image(
        session: Session,
        *,
        portfolio_id: int,
        image_id: int,
        admin_user_id: int,
    ) -> dict[str, Any]:
        detail = repository.find_portfolio_detail(session, portfolio_id)
        if detail is None:
            raise AdminPortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )
        try:
            result = CompanyPortfolioImageService.delete_image(
                session,
                user=_admin_image_user(
                    admin_user_id, detail["company_id"]
                ),
                portfolio_id=portfolio_id,
                image_id=image_id,
            )
            AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="portfolio.image_deleted",
                target_type="portfolio_image",
                target_id=image_id,
                before_data={"portfolio_id": portfolio_id},
                reason="관리자 원본 대조 수정",
                metadata={"source": "admin_portfolio_compare"},
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return result
