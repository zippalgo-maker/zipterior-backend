from typing import Any

from sqlalchemy.orm import Session

from app.modules.bulk_import import repository as bulk_import_repository
from app.modules.portfolios import public_repository


class PublicPortfolioNotFoundError(ValueError):
    pass


def _variant_from_row(
    image: dict[str, Any],
    prefix: str,
) -> dict[str, Any]:
    return {
        "path": image.get(f"{prefix}_path"),
        "width": image.get(f"{prefix}_width"),
        "height": image.get(f"{prefix}_height"),
        "size_bytes": image.get(f"{prefix}_size_bytes"),
    }


def build_public_image(
    image: dict[str, Any],
) -> dict[str, Any]:
    width = (
        image.get("medium_width")
        or image.get("large_width")
        or image.get("thumbnail_width")
    )
    height = (
        image.get("medium_height")
        or image.get("large_height")
        or image.get("thumbnail_height")
    )

    aspect_ratio = None
    if width and height:
        aspect_ratio = round(width / height, 6)

    room_code = image.get("room_code") or "etc"

    return {
        "id": image["id"],
        "portfolio_space_id": image.get("portfolio_space_id"),
        "room_code": room_code,
        "room_label": {
            "living_room": "거실",
            "kitchen": "주방",
            "master_room": "안방",
            "room": "방",
            "bathroom": "욕실",
            "entrance": "현관",
            "balcony": "발코니",
            "dressing_room": "드레스룸",
            "utility_room": "다용도실",
            "etc": "기타",
        }.get(room_code, "기타"),
        "original_filename": image.get("original_filename"),
        "large_path": image.get("large_path"),
        "medium_path": image.get("medium_path"),
        "thumbnail_path": image.get("thumbnail_path"),
        "large": _variant_from_row(image, "large"),
        "medium": _variant_from_row(image, "medium"),
        "thumbnail": _variant_from_row(image, "thumbnail"),
        "sort_order": image.get("sort_order", 0),
        "is_representative": bool(
            image.get("is_representative")
        ),
        "aspect_ratio": aspect_ratio,
        # v2.5.0: 방 전체 설명과는 별개로, 이 사진 한 장에 붙는 원본 문단.
        # 값이 없으면 프런트에서 캡션 영역 자체를 노출하지 않는다.
        "description": image.get("description"),
    }


def build_representative_image(
    portfolio: dict[str, Any],
) -> dict[str, Any] | None:
    if portfolio.get("representative_image_id") is None:
        return None

    image = {
        "id": portfolio["representative_image_id"],
        "portfolio_space_id": portfolio.get("representative_portfolio_space_id"),
        "room_code": portfolio.get(
            "representative_room_code"
        ) or "etc",
        "original_filename": portfolio.get(
            "representative_original_filename"
        ),
        "large_path": portfolio.get(
            "representative_large_path"
        ),
        "large_width": portfolio.get(
            "representative_large_width"
        ),
        "large_height": portfolio.get(
            "representative_large_height"
        ),
        "large_size_bytes": portfolio.get(
            "representative_large_size_bytes"
        ),
        "medium_path": portfolio.get(
            "representative_medium_path"
        ),
        "medium_width": portfolio.get(
            "representative_medium_width"
        ),
        "medium_height": portfolio.get(
            "representative_medium_height"
        ),
        "medium_size_bytes": portfolio.get(
            "representative_medium_size_bytes"
        ),
        "thumbnail_path": portfolio.get(
            "representative_thumbnail_path"
        ),
        "thumbnail_width": portfolio.get(
            "representative_thumbnail_width"
        ),
        "thumbnail_height": portfolio.get(
            "representative_thumbnail_height"
        ),
        "thumbnail_size_bytes": portfolio.get(
            "representative_thumbnail_size_bytes"
        ),
        "sort_order": portfolio.get(
            "representative_sort_order"
        ) or 0,
        "is_representative": True,
    }

    return build_public_image(image)


def build_public_portfolio(
    portfolio: dict[str, Any],
    *,
    keywords: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
        "id": portfolio["id"],
        "title": portfolio["title"],
        "summary": portfolio["summary"],
        "company": {
            "id": portfolio["company_id"],
            "name": portfolio["company_name"],
            "logo_path": portfolio["company_logo_path"],
            "phone": portfolio["company_phone"],
            "sido": portfolio["company_sido"],
            "sigungu": portfolio["company_sigungu"],
            "eupmyeondong": portfolio[
                "company_eupmyeondong"
            ],
            "consultation_available": portfolio[
                "consultation_available"
            ],
        },
        "complex_id": portfolio["complex_id"],
        "complex_name": portfolio["complex_name"],
        "apartment_type_id": portfolio[
            "apartment_type_id"
        ],
        "apartment_type_name": portfolio[
            "apartment_type_name"
        ],
        "pyeong_label": portfolio["pyeong_label"],
        "supply_area_m2": portfolio["supply_area_m2"],
        "exclusive_area_m2": portfolio["exclusive_area_m2"],
        "construction_scope": portfolio[
            "construction_scope"
        ],
        "budget_min": portfolio["budget_min"],
        "budget_max": portfolio["budget_max"],
        "construction_days": portfolio[
            "construction_days"
        ],
        "construction_date": portfolio[
            "construction_date"
        ],
        "representative_image_id": portfolio[
            "representative_image_id"
        ],
        "representative_large_path": portfolio[
            "representative_large_path"
        ],
        "representative_medium_path": portfolio[
            "representative_medium_path"
        ],
        "representative_thumbnail_path": portfolio[
            "representative_thumbnail_path"
        ],
        "representative_image": (
            build_representative_image(portfolio)
        ),
        "keywords": keywords,
        "view_count": portfolio["view_count"],
        "like_count": portfolio["like_count"],
        "comment_count": portfolio["comment_count"],
        "published_at": portfolio["published_at"],
        # v2.5.67(2026-08-24): near_lat/near_lng가 있는 조회에서만 값이
        # 들어있고, 그 외엔 repository가 NULL을 내려줘 자연히 None.
        # km 소수점 2자리로 반올림(예: 850m -> 0.85km) -- 표시는
        # 프론트가 1km 미만이면 m로 바꿔서 보여줌(js/app.js 참고).
        "distance_km": (
            round(portfolio["distance_km"], 2)
            if portfolio.get("distance_km") is not None
            else None
        ),
    }

    if "description" in portfolio:
        result["description"] = portfolio["description"]

    if images is not None:
        result["images"] = [
            build_public_image(image)
            for image in images
        ]

    return result


class PublicPortfolioService:
    @staticmethod
    def list_portfolios(
        session: Session,
        *,
        keyword_id: int | None,
        keyword_ids: list[int] | None,
        q: str | None,
        sido: str | None,
        sigungu: str | None,
        company_id: int | None,
        company_name: str | None,
        complex_id: int | None,
        complex_name: str | None,
        apartment_type_id: int | None,
        construction_scope: str | None,
        pyeong_min: float | None,
        pyeong_max: float | None,
        budget_min: int | None,
        budget_max: int | None,
        sort: str,
        near_lat: float | None = None,
        near_lng: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:

        if (
            pyeong_min is not None
            and pyeong_max is not None
            and pyeong_min > pyeong_max
        ):
            raise ValueError(
                "최소 평수는 최대 평수보다 클 수 없습니다."
            )

        if (
            budget_min is not None
            and budget_max is not None
            and budget_min > budget_max
        ):
            raise ValueError(
                "최소 예산은 최대 예산보다 클 수 없습니다."
            )

        portfolios = (
            public_repository.list_public_portfolios(
                session,
                keyword_id=keyword_id,
                keyword_ids=keyword_ids,
                q=q,
                sido=sido,
                sigungu=sigungu,
                company_id=company_id,
                company_name=company_name,
                complex_id=complex_id,
                complex_name=complex_name,
                apartment_type_id=apartment_type_id,
                construction_scope=construction_scope,
                pyeong_min=pyeong_min,
                pyeong_max=pyeong_max,
                budget_min=budget_min,
                budget_max=budget_max,
                sort=sort,
                near_lat=near_lat,
                near_lng=near_lng,
                limit=limit,
                offset=offset,
            )
        )

        total = public_repository.count_public_portfolios(
            session,
            keyword_id=keyword_id,
            keyword_ids=keyword_ids,
            q=q,
            sido=sido,
            sigungu=sigungu,
            company_id=company_id,
            company_name=company_name,
            complex_id=complex_id,
            complex_name=complex_name,
            apartment_type_id=apartment_type_id,
            construction_scope=construction_scope,
            pyeong_min=pyeong_min,
            pyeong_max=pyeong_max,
            budget_min=budget_min,
            budget_max=budget_max,
        )

        items = []

        for portfolio in portfolios:
            keywords = (
                public_repository
                .list_public_portfolio_keywords(
                    session,
                    portfolio_id=portfolio["id"],
                )
            )

            items.append(
                build_public_portfolio(
                    portfolio,
                    keywords=keywords,
                )
            )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


    @staticmethod
    def get_portfolio(
        session: Session,
        *,
        portfolio_id: int,
    ) -> dict[str, Any]:
        portfolio = (
            public_repository.find_public_portfolio(
                session,
                portfolio_id=portfolio_id,
            )
        )

        if portfolio is None:
            raise PublicPortfolioNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        keywords = (
            public_repository
            .list_public_portfolio_keywords(
                session,
                portfolio_id=portfolio_id,
            )
        )

        images = (
            public_repository.list_public_portfolio_images(
                session,
                portfolio_id=portfolio_id,
            )
        )

        spaces = public_repository.list_public_portfolio_spaces(
            session,
            portfolio_id=portfolio_id,
        )

        result = build_public_portfolio(
            portfolio,
            keywords=keywords,
            images=images,
        )
        result["spaces"] = spaces
        # v2.5.0 (원문 재현): 있으면 프론트가 이걸로 오늘의집 원본 순서
        # 그대로 렌더링한다. 없으면 빈 배열 -- 프론트가 기존 spaces
        # 갤러리로 자동 대체한다(에러 아님, 정상 상태).
        result["content_blocks"] = bulk_import_repository.list_content_blocks(
            session, portfolio_id=portfolio_id
        )
        return result
