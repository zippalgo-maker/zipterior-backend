"""v1.10.1(2026-08-26): reviews 모듈 최초 구현.

작성 자격 검증(목업 13번 화면 "준공 후 작성 가능"): estimate_requests.
status가 'closed'이고 본인 견적이며, 아직 리뷰를 안 쓴 경우에만 허용.
어느 업체에 리뷰를 남기는지는 estimate_request_companies에서 status=
'contracted'인 행으로 정한다(계약된 업체 = 실제로 시공한 업체)."""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.estimates import repository as estimate_repository
from app.modules.reviews import repository
from app.modules.reviews.schemas import ReviewCreateRequest


class ReviewNotFoundError(ValueError):
    pass


class ReviewAccessDeniedError(ValueError):
    pass


class ReviewValidationError(ValueError):
    pass


class ReviewStateConflictError(ValueError):
    pass


def _build(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "estimate_request_id": row["estimate_request_id"],
        "customer_id": row["customer_id"],
        "company": {"id": row["company_id"], "name": row.get("company_name") or ""},
        "portfolio_id": row["portfolio_id"],
        "rating": row["rating"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


class ReviewService:
    @staticmethod
    def create(session: Session, *, user: dict[str, Any], payload: ReviewCreateRequest) -> dict[str, Any]:
        if user.get("role") != "customer":
            raise ReviewAccessDeniedError("일반회원만 리뷰를 작성할 수 있습니다.")
        estimate = estimate_repository.find_estimate_by_id(session, estimate_id=payload.estimate_request_id)
        if estimate is None or estimate["customer_id"] != user["id"]:
            raise ReviewNotFoundError("견적 요청을 찾을 수 없습니다.")
        if estimate["status"] != "closed":
            raise ReviewStateConflictError("준공(완료) 처리된 견적만 리뷰를 작성할 수 있습니다.")
        if repository.find_review_by_estimate(session, estimate_id=payload.estimate_request_id):
            raise ReviewStateConflictError("이미 이 견적에 리뷰를 작성했습니다.")
        assignments = estimate_repository.list_assignments(session, estimate_id=payload.estimate_request_id)
        contracted = next((a for a in assignments if a["status"] == "contracted"), None)
        if contracted is None:
            raise ReviewValidationError("계약된 업체 정보를 찾을 수 없습니다.")
        row = repository.create_review(
            session,
            estimate_id=payload.estimate_request_id,
            customer_id=user["id"],
            company_id=contracted["company_id"],
            portfolio_id=estimate.get("portfolio_id"),
            rating=payload.rating,
            content=payload.content,
        )
        row["company_name"] = contracted["company_name"]
        return _build(row)

    @staticmethod
    def list_by_company(session: Session, *, company_id: int, limit: int, offset: int) -> dict[str, Any]:
        rows = repository.list_reviews_by_company(session, company_id=company_id, limit=limit, offset=offset)
        return {
            "items": [_build(row) for row in rows],
            "total": repository.count_reviews_by_company(session, company_id=company_id),
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def list_mine(session: Session, *, user: dict[str, Any], limit: int, offset: int) -> dict[str, Any]:
        if user.get("role") != "customer":
            raise ReviewAccessDeniedError("일반회원만 조회할 수 있습니다.")
        rows = repository.list_reviews_mine(session, customer_id=user["id"], limit=limit, offset=offset)
        return {
            "items": [_build(row) for row in rows],
            "total": repository.count_reviews_mine(session, customer_id=user["id"]),
            "limit": limit,
            "offset": offset,
        }
