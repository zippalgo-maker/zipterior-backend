from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def build_public_filter_sql(
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
) -> tuple[list[str], dict[str, Any]]:
    conditions = [
        "p.status = 'approved'",
        "p.deleted_at IS NULL",
        "c.status = 'active'",
    ]

    parameters: dict[str, Any] = {}

    # ------------------------------------------------------
    # 기존 단일 키워드 검색
    # ------------------------------------------------------
    if keyword_id is not None:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM portfolio_keyword_links AS filter_pkl
                JOIN portfolio_keywords AS filter_pk
                  ON filter_pk.id = filter_pkl.keyword_id
                WHERE filter_pkl.portfolio_id = p.id
                  AND filter_pkl.keyword_id = :keyword_id
                  AND filter_pk.is_active = TRUE
            )
            """
        )
        parameters["keyword_id"] = keyword_id

    # ------------------------------------------------------
    # 다중 키워드 AND 검색
    #
    # keyword_ids=7&keyword_ids=8&keyword_ids=13
    # → 세 키워드를 모두 가지고 있어야 통과
    # ------------------------------------------------------
    if keyword_ids:
        placeholders = []

        for index, value in enumerate(keyword_ids):
            key = f"keyword_ids_{index}"
            placeholders.append(f":{key}")
            parameters[key] = value

        conditions.append(
            f"""
            (
                SELECT COUNT(DISTINCT filter_multi_pkl.keyword_id)
                FROM portfolio_keyword_links AS filter_multi_pkl
                JOIN portfolio_keywords AS filter_multi_pk
                  ON filter_multi_pk.id =
                     filter_multi_pkl.keyword_id
                WHERE filter_multi_pkl.portfolio_id = p.id
                  AND filter_multi_pkl.keyword_id IN (
                      {", ".join(placeholders)}
                  )
                  AND filter_multi_pk.is_active = TRUE
            ) = :keyword_ids_count
            """
        )

        parameters["keyword_ids_count"] = len(
            keyword_ids
        )

    # ------------------------------------------------------
    # 통합검색
    # ------------------------------------------------------
    if q is not None:
        conditions.append(
            """
            (
                p.title ILIKE :q
                OR p.summary ILIKE :q
                OR p.description ILIKE :q
                OR c.name ILIKE :q
                OR ac.name ILIKE :q
            )
            """
        )
        parameters["q"] = f"%{q}%"

    # ------------------------------------------------------
    # 지역
    # ------------------------------------------------------
    if sido is not None:
        conditions.append("c.sido = :sido")
        parameters["sido"] = sido

    if sigungu is not None:
        conditions.append("c.sigungu = :sigungu")
        parameters["sigungu"] = sigungu

    # ------------------------------------------------------
    # 업체
    # ------------------------------------------------------
    if company_id is not None:
        conditions.append("p.company_id = :company_id")
        parameters["company_id"] = company_id

    if company_name is not None:
        conditions.append(
            "c.name ILIKE :company_name"
        )
        parameters["company_name"] = (
            f"%{company_name}%"
        )

    # ------------------------------------------------------
    # 아파트 단지
    # ------------------------------------------------------
    if complex_id is not None:
        conditions.append(
            "p.complex_id = :complex_id"
        )
        parameters["complex_id"] = complex_id

    if complex_name is not None:
        conditions.append(
            "ac.name ILIKE :complex_name"
        )
        parameters["complex_name"] = (
            f"%{complex_name}%"
        )

    # ------------------------------------------------------
    # 아파트 타입
    # ------------------------------------------------------
    if apartment_type_id is not None:
        conditions.append(
            "p.apartment_type_id = :apartment_type_id"
        )
        parameters[
            "apartment_type_id"
        ] = apartment_type_id

    # ------------------------------------------------------
    # 시공 범위
    # ------------------------------------------------------
    if construction_scope is not None:
        conditions.append(
            "p.construction_scope = :construction_scope"
        )
        parameters[
            "construction_scope"
        ] = construction_scope

    # ------------------------------------------------------
    # 평형
    #
    # 아파트의 24평/34평 등은 공급면적 기준을 우선 사용.
    # 공급면적이 없을 경우에만 전용면적을 fallback.
    # ------------------------------------------------------
    pyeong_expression = (
        "(COALESCE("
        "apt.supply_area_m2, "
        "apt.exclusive_area_m2"
        ") / 3.305785)"
    )

    if pyeong_min is not None:
        conditions.append(
            f"{pyeong_expression} >= :pyeong_min"
        )
        parameters["pyeong_min"] = pyeong_min

    if pyeong_max is not None:
        conditions.append(
            f"{pyeong_expression} <= :pyeong_max"
        )
        parameters["pyeong_max"] = pyeong_max

    # ------------------------------------------------------
    # 예산
    #
    # 포트폴리오 예산범위와 사용자가 지정한 검색범위가
    # 서로 겹치는 경우 검색.
    # ------------------------------------------------------
    if budget_min is not None:
        conditions.append(
            "p.budget_max >= :budget_min"
        )
        parameters["budget_min"] = budget_min

    if budget_max is not None:
        conditions.append(
            "p.budget_min <= :budget_max"
        )
        parameters["budget_max"] = budget_max

    return conditions, parameters


def list_public_portfolios(
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
) -> list[dict[str, Any]]:
    conditions, parameters = build_public_filter_sql(
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

    # v2.5.42(2026-08-23): 모바일 홈 피드 "내 위치와 가까운 순" 정렬.
    # apartment_complexes에 위경도가 이미 있고(NOT NULL, 좌표 인덱스도
    # 있음) 승인 포트폴리오는 전부 complex_id가 연결돼 있어서(2026-08-23
    # 실측 0건 예외) 신규 컬럼/테이블 없이 하버사인 공식만 추가하면
    # 된다. lat/lng가 안 오면(위치 권한 거부 등) 그냥 latest로 안전
    # 폴백 -- 프론트가 강제로 위치를 요구하지 않아도 되게.
    #
    # v2.5.67(2026-08-24): 이 하버사인 계산은 원래 ORDER BY 안에서만
    # 쓰이고 값 자체는 응답에 안 내려줬었다. PC 지도 "내 주변 시공사례"
    # 위젯이 거리를 보여주려고 프론트에서 지도 뷰포트에 이미 로드된
    # complexes 배열을 따로 뒤져서 거리를 재계산했는데, 그 배열이
    # 해당 시점에 그 단지를 아직 안 갖고 있으면(흔한 케이스) 거리가
    # 조용히 빈 값으로 생략됐다 -- "가장 가까운 포폴 거리 표시가 안
    # 보인다"는 사용자 리포트의 원인. 서버가 정렬을 위해 이미 정확히
    # 계산해두는 값이니 같은 식을 SELECT에도 노출해서(distance_km)
    # 프론트가 재계산/재조회 없이 그대로 쓰게 한다(CLAUDE.md 4번
    # "서버가 스스로 계산해서 채워 넣을 수 있으면 그 방향" 원칙).
    # near_lat/near_lng가 오면 sort 값과 무관하게(예: latest로 다른
    # 정렬을 쓰면서도 거리만 같이 보고 싶은 경우 대비) distance_km을
    # 채워준다 -- ac.latitude/longitude가 NULL인 단지는 SQL의 NULL
    # 전파로 distance_km도 자연히 NULL(별도 CASE 불필요).
    if near_lat is not None and near_lng is not None:
        distance_expr = """
            (6371 * acos(LEAST(1, GREATEST(-1,
                cos(radians(:near_lat)) * cos(radians(ac.latitude))
                    * cos(radians(ac.longitude) - radians(:near_lng))
                + sin(radians(:near_lat)) * sin(radians(ac.latitude))
            ))))
        """
        parameters["near_lat"] = near_lat
        parameters["near_lng"] = near_lng
    else:
        distance_expr = "NULL"

    if sort == "nearest" and near_lat is not None and near_lng is not None:
        order_by = f"""
            CASE WHEN ac.latitude IS NULL THEN 1 ELSE 0 END ASC,
            {distance_expr} ASC,
            p.published_at DESC,
            p.id DESC
        """
    elif sort == "popular":
        order_by = """
            p.view_count DESC,
            p.like_count DESC,
            p.comment_count DESC,
            p.published_at DESC,
            p.id DESC
        """
    else:
        order_by = """
            p.published_at DESC,
            p.id DESC
        """

    parameters.update(
        {
            "limit": limit,
            "offset": offset,
        }
    )

    rows = session.execute(
        text(
            f"""
            SELECT
                p.id,
                p.title,
                p.summary,

                p.company_id,
                c.name AS company_name,
                c.logo_path AS company_logo_path,
                c.phone AS company_phone,
                c.sido AS company_sido,
                c.sigungu AS company_sigungu,
                c.eupmyeondong
                    AS company_eupmyeondong,
                c.consultation_available,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name
                    AS apartment_type_name,
                apt.pyeong_label,
                apt.supply_area_m2,
                apt.exclusive_area_m2,

                p.construction_scope,
                p.budget_min,
                p.budget_max,
                p.construction_days,
                p.construction_date,

                p.representative_image_id,
                pi.room_code AS representative_room_code,
                pi.original_filename
                    AS representative_original_filename,
                pi.large_path
                    AS representative_large_path,
                pi.large_width
                    AS representative_large_width,
                pi.large_height
                    AS representative_large_height,
                pi.large_size_bytes
                    AS representative_large_size_bytes,
                pi.medium_path
                    AS representative_medium_path,
                pi.medium_width
                    AS representative_medium_width,
                pi.medium_height
                    AS representative_medium_height,
                pi.medium_size_bytes
                    AS representative_medium_size_bytes,
                pi.thumbnail_path
                    AS representative_thumbnail_path,
                pi.thumbnail_width
                    AS representative_thumbnail_width,
                pi.thumbnail_height
                    AS representative_thumbnail_height,
                pi.thumbnail_size_bytes
                    AS representative_thumbnail_size_bytes,
                pi.sort_order
                    AS representative_sort_order,

                p.view_count,
                p.like_count,
                p.comment_count,
                p.published_at,

                {distance_expr} AS distance_km

            FROM portfolios AS p

            JOIN companies AS c
              ON c.id = p.company_id

            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id

            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id

            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id

            WHERE {" AND ".join(conditions)}

            ORDER BY {order_by}

            LIMIT :limit
            OFFSET :offset
            """
        ),
        parameters,
    ).mappings().all()

    return [dict(row) for row in rows]


def count_public_portfolios(
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
) -> int:
    conditions, parameters = build_public_filter_sql(
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

    return int(
        session.execute(
            text(
                f"""
                SELECT COUNT(*)

                FROM portfolios AS p

                JOIN companies AS c
                  ON c.id = p.company_id

                LEFT JOIN apartment_complexes AS ac
                  ON ac.id = p.complex_id

                LEFT JOIN apartment_types AS apt
                  ON apt.id = p.apartment_type_id

                WHERE {" AND ".join(conditions)}
                """
            ),
            parameters,
        ).scalar_one()
    )


def find_public_portfolio(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.title,
                p.summary,
                p.description,

                p.company_id,
                c.name AS company_name,
                c.logo_path AS company_logo_path,
                c.phone AS company_phone,
                c.sido AS company_sido,
                c.sigungu AS company_sigungu,
                c.eupmyeondong AS company_eupmyeondong,
                c.consultation_available,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name AS apartment_type_name,
                apt.pyeong_label,
                apt.supply_area_m2,
                apt.exclusive_area_m2,

                p.construction_scope,
                p.budget_min,
                p.budget_max,
                p.construction_days,
                p.construction_date,

                p.representative_image_id,
                pi.room_code AS representative_room_code,
                pi.original_filename
                    AS representative_original_filename,
                pi.large_path
                    AS representative_large_path,
                pi.large_width
                    AS representative_large_width,
                pi.large_height
                    AS representative_large_height,
                pi.large_size_bytes
                    AS representative_large_size_bytes,
                pi.medium_path
                    AS representative_medium_path,
                pi.medium_width
                    AS representative_medium_width,
                pi.medium_height
                    AS representative_medium_height,
                pi.medium_size_bytes
                    AS representative_medium_size_bytes,
                pi.thumbnail_path
                    AS representative_thumbnail_path,
                pi.thumbnail_width
                    AS representative_thumbnail_width,
                pi.thumbnail_height
                    AS representative_thumbnail_height,
                pi.thumbnail_size_bytes
                    AS representative_thumbnail_size_bytes,
                pi.sort_order
                    AS representative_sort_order,

                p.view_count,
                p.like_count,
                p.comment_count,
                p.published_at
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            WHERE p.id = :portfolio_id
              AND p.status = 'approved'
              AND p.deleted_at IS NULL
              AND c.status = 'active'
            LIMIT 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def list_public_portfolio_keywords(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                pk.id,
                pk.name,
                pk.category,
                pk.sort_order
            FROM portfolio_keyword_links AS pkl
            JOIN portfolio_keywords AS pk
              ON pk.id = pkl.keyword_id
            WHERE pkl.portfolio_id = :portfolio_id
              AND pk.is_active = TRUE
            ORDER BY pk.category, pk.sort_order, pk.id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]



def list_public_portfolio_spaces(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                space_code,
                space_name,
                space_number,
                description,
                sort_order
            FROM portfolio_spaces
            WHERE portfolio_id = :portfolio_id
            ORDER BY sort_order, space_number, id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]



def list_public_portfolio_images(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                portfolio_space_id,
                room_code,
                original_filename,
                large_path,
                large_width,
                large_height,
                large_size_bytes,
                medium_path,
                medium_width,
                medium_height,
                medium_size_bytes,
                thumbnail_path,
                thumbnail_width,
                thumbnail_height,
                thumbnail_size_bytes,
                sort_order,
                is_representative,
                description
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
              AND processing_status = 'completed'
            ORDER BY
                is_representative DESC,
                sort_order,
                id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]
