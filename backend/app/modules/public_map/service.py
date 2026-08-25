import re
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modules.public_map import kakao_search_client, repository


class PublicCompanyNotFoundError(ValueError):
    pass


class PublicComplexNotFoundError(ValueError):
    pass


class PublicMapService:
    @staticmethod
    def get_company(session: Session, company_id: int) -> dict[str, Any]:
        company = repository.find_public_company(session, company_id)
        if company is None:
            raise PublicCompanyNotFoundError("공개된 업체를 찾을 수 없습니다.")
        company["service_regions"] = repository.list_company_regions(session, company_id)
        company["portfolios"] = repository.list_company_portfolios(session, company_id)
        return company

    @staticmethod
    def list_complexes(session: Session, **kwargs):
        items = repository.list_complexes(session, **kwargs)
        total = repository.count_complexes(
            session,
            q=kwargs.get("q"),
            sido=kwargs.get("sido"),
            sigungu=kwargs.get("sigungu"),
        )
        return {
            "items": items,
            "total": total,
            "limit": kwargs["limit"],
            "offset": kwargs["offset"],
        }

    @staticmethod
    def get_complex(session: Session, complex_id: int):
        item = repository.find_complex(session, complex_id)
        if item is None:
            raise PublicComplexNotFoundError("아파트 단지를 찾을 수 없습니다.")
        item["apartment_types"] = repository.list_apartment_types(
            session,
            complex_id=complex_id,
            limit=100,
            offset=0,
        )
        item["images"] = repository.list_complex_images(
            session, complex_id=complex_id
        )
        return item

    @staticmethod
    def list_apartment_types(
        session: Session,
        *,
        complex_id: int,
        limit: int,
        offset: int,
    ):
        if repository.find_complex(session, complex_id) is None:
            raise PublicComplexNotFoundError("아파트 단지를 찾을 수 없습니다.")
        return {
            "items": repository.list_apartment_types(
                session,
                complex_id=complex_id,
                limit=limit,
                offset=offset,
            ),
            "total": repository.count_apartment_types(session, complex_id),
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def list_markers(session: Session, **kwargs):
        items = repository.list_markers(session, **kwargs)
        return {"items": items, "total": len(items)}

    _NAME_SUFFIX_WORDS = ("아파트", "오피스텔", "단지")

    @staticmethod
    def _normalize_place_name(name: str) -> str:
        """2026-08-25 실측 수정: 처음엔 공백제거+소문자만 하는 완전일치
        비교였는데, 실제로 "미사역"으로 검색해보니 DB엔 "망월동
        미사역파라곤"(동 이름이 접두로 붙음)으로 저장돼 있고 카카오는
        "미사역파라곤아파트"(건물유형 접미가 붙음)로 돌아와서 정규화해도
        문자열이 달라(둘 다 안 걸러짐) 같은 단지가 목록에 두 번 뜨는
        걸 실측으로 확인했다. 그래서 (1) 괄호 블록(예: "(12-1BL)")
        제거 (2) 아파트/오피스텔/단지 같은 흔한 접미어 제거까지 하고,
        완전일치 대신 포함관계(부분 문자열)로 비교한다(_is_duplicate)."""
        normalized = re.sub(r"\s+", "", name or "").lower()
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        for suffix in PublicMapService._NAME_SUFFIX_WORDS:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    @staticmethod
    def _is_duplicate_name(candidate_key: str, existing_keys: set[str]) -> bool:
        # 너무 짧은 키(예: "역" 한 글자)까지 부분포함으로 비교하면 무관한
        # 결과끼리 오매칭될 수 있어, 최소 길이 미만이면 포함관계 비교를
        # 건너뛰고 완전일치만 본다.
        if not candidate_key:
            return False
        if candidate_key in existing_keys:
            return True
        if len(candidate_key) < 4:
            return False
        return any(
            len(key) >= 4 and (candidate_key in key or key in candidate_key)
            for key in existing_keys
        )

    @staticmethod
    def search(session: Session, *, q: str, limit: int):
        """2026-08-25: 통합검색에 카카오 로컬 검색을 접목 -- 집테리어
        DB(단지/업체) 결과를 항상 먼저 채우고, 자리가 남으면(예: DB에
        없는 아파트/오피스텔/지하철역) 카카오 결과로 나머지를 채운다.
        이미 DB 결과와 같은 단지로 보이면 중복으로 보고 건너뛴다(예:
        "미사역파라곤"이 DB에 있으면 카카오가 "미사역파라곤아파트"로
        줘도 중복 표시하지 않음, 이름 정규화+포함관계 비교는
        _normalize_place_name/_is_duplicate_name 참고). DB에 전혀
        없는 이름으로 검색하면(예: "미사역물랑루즈") DB 쪽은 0건이라
        카카오 결과만 남는다."""
        items = repository.search_map(session, q=q, limit=limit)
        remaining = limit - len(items)
        if remaining > 0:
            existing_names = {
                PublicMapService._normalize_place_name(item["name"])
                for item in items
            }
            try:
                places = kakao_search_client.search_places(q, size=remaining + 5)
            except Exception:
                places = []
            for place in places:
                if len(items) >= limit:
                    break
                normalized = PublicMapService._normalize_place_name(place["name"])
                if PublicMapService._is_duplicate_name(normalized, existing_names):
                    continue
                existing_names.add(normalized)
                items.append({
                    "result_type": "place",
                    "id": None,
                    "name": place["name"],
                    "sido": None,
                    "sigungu": None,
                    "eupmyeondong": None,
                    "latitude": Decimal(str(place["latitude"])),
                    "longitude": Decimal(str(place["longitude"])),
                    "portfolio_count": 0,
                    "source": "kakao",
                    "place_category": place["place_category"],
                })
        return {"items": items, "total": len(items)}

    @staticmethod
    def cluster_grid_summary(session: Session, *, north, south, east, west, cell_size: float):
        cells = repository.cluster_grid_summary(
            session, north=north, south=south, east=east, west=west, cell_size=cell_size
        )
        return {"cells": cells}

    @staticmethod
    def cluster_cell_degrees(zoom: int) -> Decimal | None:
        # Korea-focused grid sizes. zoom >= 16 returns individual markers.
        if zoom <= 7:
            return Decimal("0.500")
        if zoom <= 9:
            return Decimal("0.200")
        if zoom <= 11:
            return Decimal("0.080")
        if zoom <= 13:
            return Decimal("0.030")
        if zoom <= 15:
            return Decimal("0.012")
        return None

    @staticmethod
    def viewport(
        session: Session,
        *,
        marker_type: str,
        zoom: int,
        north: float,
        south: float,
        east: float,
        west: float,
        sido: str | None,
        sigungu: str | None,
        limit: int,
        consultation_available: bool | None,
        premium_only: bool,
        has_portfolio: bool,
    ) -> dict[str, Any]:
        source_markers = repository.list_markers(
            session,
            marker_type=marker_type,
            north=north,
            south=south,
            east=east,
            west=west,
            sido=sido,
            sigungu=sigungu,
            limit=limit,
            consultation_available=consultation_available,
            premium_only=premium_only,
            has_portfolio=has_portfolio,
        )

        cell = PublicMapService.cluster_cell_degrees(zoom)
        if cell is None:
            items = []
            for marker in source_markers:
                item = marker.copy()
                item.update(
                    item_type="marker",
                    cluster_id=None,
                    count=1,
                    premium_count=1 if marker.get("is_premium") else 0,
                )
                items.append(item)
        else:
            items = repository.cluster_markers(
                source_markers,
                marker_type=marker_type,
                cell_degrees=cell,
            )

        return {
            "zoom": zoom,
            "clustered": cell is not None,
            "cluster_cell_degrees": cell,
            "items": items,
            "total_items": len(items),
            "source_marker_count": len(source_markers),
        }
