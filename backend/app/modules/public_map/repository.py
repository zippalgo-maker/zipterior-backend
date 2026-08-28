from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.modules.feature_flags import repository as feature_flags_repository

# v2.5.1: 관리자가 "지도 마커/단지 기본정보에서 아파트·오피스텔 유형별로
# 노출 여부를 결정"할 수 있게 하는 설정. system_features 테이블을
# 그대로 재사용(스키마 변경 없음). 기본값은 둘 다 노출 -- 설정 행이
# 아직 없어도(운영 반영 전 등) 기존과 동일하게 전부 보이도록 안전한
# 기본값을 둔다. V2.5.0_PLAN.md 참고.
MAP_COMPLEX_TYPE_VISIBILITY_KEY = "map_complex_type_visibility"


def _type_visibility(session: Session) -> tuple[bool, bool]:
    feature = feature_flags_repository.get_base_feature(
        session, MAP_COMPLEX_TYPE_VISIBILITY_KEY
    )
    settings = (feature or {}).get("settings") or {}
    apartment_visible = settings.get("apartment_visible", True) is not False
    officetel_visible = settings.get("officetel_visible", True) is not False
    return apartment_visible, officetel_visible


def _type_visibility_conditions(session: Session, alias: str = "ac") -> list[str]:
    """미분류(complex_type IS NULL) 단지는 숨김 대상이 아니다 -- 노출을
    끄는 건 명확히 그 유형으로 분류된 단지만 대상으로 한다."""
    apartment_visible, officetel_visible = _type_visibility(session)
    conditions = []
    if not apartment_visible:
        conditions.append(f"{alias}.complex_type IS DISTINCT FROM 'apartment'")
    if not officetel_visible:
        conditions.append(f"{alias}.complex_type IS DISTINCT FROM 'officetel'")
    return conditions


def _membership_join(alias: str = "c") -> str:
    return f"""
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(mp.map_priority, 0) AS map_priority
            FROM company_memberships cm
            JOIN membership_plans mp
              ON mp.id = cm.plan_id
             AND mp.is_active = TRUE
            WHERE cm.company_id = {alias}.id
              AND cm.status = 'active'
              AND (cm.expires_at IS NULL OR cm.expires_at > NOW())
            ORDER BY mp.map_priority DESC, cm.id DESC
            LIMIT 1
        ) membership ON TRUE
    """


def find_public_company(session: Session, company_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            f"""
            SELECT
                c.id,c.name,c.slug,c.representative_name,c.phone,c.email::text AS email,
                c.address,c.address_detail,c.sido,c.sigungu,c.eupmyeondong,c.latitude,c.longitude,
                c.intro,c.logo_path,c.website_url,c.kakao_url,c.consultation_available,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status='approved' AND p.deleted_at IS NULL
                ) AS portfolio_count,
                COALESCE(css.company_exposure_score,0) AS exposure_score,
                COALESCE(membership.map_priority,0) AS map_priority,
                (COALESCE(membership.map_priority,0) > 0) AS is_premium
            FROM companies c
            LEFT JOIN portfolios p ON p.company_id=c.id
            LEFT JOIN company_score_snapshots css ON css.company_id=c.id
            {_membership_join('c')}
            -- is_visible_on_map은 지도 마커 전용 값이다. 공개 포트폴리오에서 연결된
            -- 활성 업체 상세까지 숨기던 이전 조건은 제거하고 상태로 공개 여부를 판단한다.
            WHERE c.id=:company_id
              AND c.status='active'
              AND c.deleted_at IS NULL
            GROUP BY c.id,css.company_exposure_score,membership.map_priority
            """
        ),
        {"company_id": company_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


# v2.5.x: 다건 견적요청 "우리 지역 등록 파트너" 후보용. 실제 서비스지역은
# companies.sido(비어있는 경우가 많음, reference_zipterior_docs 참고)가
# 아니라 company_service_regions 조인 테이블이 정답이라 find_public_company
# 등 기존 함수와 같은 방식으로 그걸 기준으로 조회한다.
def list_public_companies_by_region(
    session: Session,
    *,
    sido: str | None,
    sigungu: str | None,
    exclude_company_ids: list[int] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    exclude_ids = list(exclude_company_ids) if exclude_company_ids else [0]
    stmt = text(
        """
        SELECT c.id, c.name, c.logo_path, csr.sido, csr.sigungu,
               COUNT(DISTINCT p.id) FILTER (
                   WHERE p.status='approved' AND p.deleted_at IS NULL
               ) AS portfolio_count
        FROM companies c
        JOIN company_service_regions csr ON csr.company_id = c.id
        LEFT JOIN portfolios p ON p.company_id = c.id
        WHERE c.status='active' AND c.deleted_at IS NULL
          AND c.id NOT IN :exclude_ids
          AND (CAST(:sido AS text) IS NULL OR csr.sido = CAST(:sido AS text))
          AND (CAST(:sigungu AS text) IS NULL OR csr.sigungu = CAST(:sigungu AS text))
        GROUP BY c.id, csr.sido, csr.sigungu
        ORDER BY portfolio_count DESC, c.id
        LIMIT :limit
        """
    ).bindparams(bindparam("exclude_ids", expanding=True))
    rows = session.execute(
        stmt,
        {"sido": sido, "sigungu": sigungu, "exclude_ids": exclude_ids, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_company_regions(session: Session, company_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT sido,sigungu,eupmyeondong,is_primary
            FROM company_service_regions
            WHERE company_id=:company_id
            ORDER BY is_primary DESC,id
            """
        ),
        {"company_id": company_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_company_portfolios(
    session: Session,
    company_id: int,
    limit: int = 12,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                p.id,p.title,p.summary,
                pi.thumbnail_path AS representative_thumbnail_path,
                p.view_count,p.like_count,p.published_at
            FROM portfolios p
            LEFT JOIN portfolio_images pi ON pi.id=p.representative_image_id
            WHERE p.company_id=:company_id
              AND p.status='approved'
              AND p.deleted_at IS NULL
            ORDER BY p.published_at DESC,p.id DESC
            LIMIT :limit
            """
        ),
        {"company_id": company_id, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def _complex_filters(session, q, sido, sigungu):
    cond = ["ac.is_active=TRUE", *_type_visibility_conditions(session)]
    params = {}
    if q:
        cond.append(
            "(ac.name ILIKE :q OR ac.road_address ILIKE :q OR ac.jibun_address ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    if sido:
        cond.append("ac.sido=:sido")
        params["sido"] = sido
    if sigungu:
        cond.append("ac.sigungu=:sigungu")
        params["sigungu"] = sigungu
    return cond, params


def list_complexes(session: Session, *, q=None, sido=None, sigungu=None, limit=50, offset=0):
    cond, params = _complex_filters(session, q, sido, sigungu)
    params.update(limit=limit, offset=offset)
    rows = session.execute(
        text(
            f"""
            SELECT
                ac.id,ac.name,ac.sido,ac.sigungu,ac.eupmyeondong,
                ac.latitude,ac.longitude,ac.completion_year,
                ac.household_count,ac.building_count,
                COUNT(DISTINCT apt.id) AS apartment_type_count,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status='approved' AND p.deleted_at IS NULL
                ) AS portfolio_count
            FROM apartment_complexes ac
            LEFT JOIN apartment_types apt ON apt.complex_id=ac.id
            LEFT JOIN portfolios p ON p.complex_id=ac.id
            WHERE {' AND '.join(cond)}
            GROUP BY ac.id
            ORDER BY portfolio_count DESC,ac.name,ac.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def count_complexes(session: Session, *, q=None, sido=None, sigungu=None):
    cond, params = _complex_filters(session, q, sido, sigungu)
    return int(
        session.execute(
            text(
                f"SELECT COUNT(*) FROM apartment_complexes ac WHERE {' AND '.join(cond)}"
            ),
            params,
        ).scalar_one()
    )


def find_complex(session: Session, complex_id: int):
    cond = ["ac.id=:id", "ac.is_active=TRUE", *_type_visibility_conditions(session)]
    row = session.execute(
        text(
            f"""
            SELECT
                ac.id,ac.name,ac.sido,ac.sigungu,ac.eupmyeondong,
                ac.road_address,ac.jibun_address,ac.latitude,ac.longitude,
                ac.completion_year,ac.household_count,ac.building_count,
                ac.parking_count,ac.heating_type,ac.builder_name,
                COUNT(DISTINCT apt.id) AS apartment_type_count,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status='approved' AND p.deleted_at IS NULL
                ) AS portfolio_count
            FROM apartment_complexes ac
            LEFT JOIN apartment_types apt ON apt.complex_id=ac.id
            LEFT JOIN portfolios p ON p.complex_id=ac.id
            WHERE {' AND '.join(cond)}
            GROUP BY ac.id
            """
        ),
        {"id": complex_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def list_complex_images(session: Session, *, complex_id: int):
    rows = session.execute(
        text(
            """
            SELECT id, image_path, thumbnail_path, width, height,
                   sort_order, is_representative
            FROM apartment_complex_images
            WHERE complex_id = :complex_id
            ORDER BY is_representative DESC, sort_order, id
            """
        ),
        {"complex_id": complex_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_apartment_types(session: Session, *, complex_id: int, limit=100, offset=0):
    rows = session.execute(
        text(
            """
            SELECT
                apt.id,apt.complex_id,apt.type_name,apt.supply_area_m2,
                apt.exclusive_area_m2,apt.pyeong_label,apt.room_count,
                apt.bathroom_count,apt.floor_plan_path,
                apt.has_basic_layout,apt.has_expanded_layout,apt.sort_order,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status='approved' AND p.deleted_at IS NULL
                ) AS portfolio_count
            FROM apartment_types apt
            LEFT JOIN portfolios p ON p.apartment_type_id=apt.id
            WHERE apt.complex_id=:complex_id
            GROUP BY apt.id
            ORDER BY apt.sort_order,apt.id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"complex_id": complex_id, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows]


def count_apartment_types(session: Session, complex_id: int):
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM apartment_types WHERE complex_id=:id"),
            {"id": complex_id},
        ).scalar_one()
    )


def _bbox_filters(alias: str, north, south, east, west, sido, sigungu):
    cond = []
    params: dict[str, Any] = {}
    if north is not None:
        cond.append(f"{alias}.latitude <= :north")
        params["north"] = north
    if south is not None:
        cond.append(f"{alias}.latitude >= :south")
        params["south"] = south
    if east is not None:
        cond.append(f"{alias}.longitude <= :east")
        params["east"] = east
    if west is not None:
        cond.append(f"{alias}.longitude >= :west")
        params["west"] = west
    if sido:
        cond.append(f"{alias}.sido=:sido")
        params["sido"] = sido
    if sigungu:
        cond.append(f"{alias}.sigungu=:sigungu")
        params["sigungu"] = sigungu
    return cond, params


def list_markers(
    session: Session,
    *,
    marker_type: str,
    north=None,
    south=None,
    east=None,
    west=None,
    sido=None,
    sigungu=None,
    limit=1000,
    consultation_available=None,
    premium_only=False,
    has_portfolio=False,
):
    if marker_type == "company":
        cond = [
            "c.status='active'",
            "c.is_visible_on_map=TRUE",
            "c.deleted_at IS NULL",
            "c.latitude IS NOT NULL",
            "c.longitude IS NOT NULL",
        ]
        bbox_cond, params = _bbox_filters(
            "c", north, south, east, west, sido, sigungu
        )
        cond.extend(bbox_cond)
        params["limit"] = limit
        if consultation_available is not None:
            cond.append("c.consultation_available=:consultation_available")
            params["consultation_available"] = consultation_available
        if premium_only:
            cond.append("COALESCE(membership.map_priority,0) > 0")
        if has_portfolio:
            cond.append(
                "EXISTS (SELECT 1 FROM portfolios p2 WHERE p2.company_id=c.id "
                "AND p2.status='approved' AND p2.deleted_at IS NULL)"
            )

        rows = session.execute(
            text(
                f"""
                SELECT
                    c.id,'company' AS marker_type,c.name,c.latitude,c.longitude,
                    c.sido,c.sigungu,c.eupmyeondong,
                    COUNT(DISTINCT p.id) FILTER (
                        WHERE p.status='approved' AND p.deleted_at IS NULL
                    ) AS portfolio_count,
                    NULL::bigint AS apartment_type_count,
                    c.consultation_available,c.logo_path,
                    COALESCE(css.company_exposure_score,0) AS exposure_score,
                    COALESCE(membership.map_priority,0) AS map_priority,
                    (COALESCE(membership.map_priority,0) > 0) AS is_premium,
                    CASE WHEN COALESCE(membership.map_priority,0) > 0
                         THEN 'premium' ELSE 'standard' END AS marker_level
                FROM companies c
                LEFT JOIN portfolios p ON p.company_id=c.id
                LEFT JOIN company_score_snapshots css ON css.company_id=c.id
                {_membership_join('c')}
                WHERE {' AND '.join(cond)}
                GROUP BY c.id,css.company_exposure_score,membership.map_priority
                ORDER BY
                    COALESCE(membership.map_priority,0) DESC,
                    COALESCE(css.company_exposure_score,0) DESC,
                    portfolio_count DESC,
                    c.id
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    else:
        cond = ["ac.is_active=TRUE", *_type_visibility_conditions(session)]
        bbox_cond, params = _bbox_filters(
            "ac", north, south, east, west, sido, sigungu
        )
        cond.extend(bbox_cond)
        params["limit"] = limit
        if has_portfolio:
            cond.append(
                "EXISTS (SELECT 1 FROM portfolios p2 WHERE p2.complex_id=ac.id "
                "AND p2.status='approved' AND p2.deleted_at IS NULL)"
            )

        rows = session.execute(
            text(
                f"""
                SELECT
                    ac.id,'complex' AS marker_type,ac.name,ac.latitude,ac.longitude,
                    ac.sido,ac.sigungu,ac.eupmyeondong,
                    COUNT(DISTINCT p.id) FILTER (
                        WHERE p.status='approved' AND p.deleted_at IS NULL
                    ) AS portfolio_count,
                    COUNT(DISTINCT apt.id) AS apartment_type_count,
                    NULL::boolean AS consultation_available,
                    NULL::text AS logo_path,NULL::numeric AS exposure_score,
                    NULL::integer AS map_priority,NULL::boolean AS is_premium,
                    NULL::text AS marker_level
                FROM apartment_complexes ac
                LEFT JOIN apartment_types apt ON apt.complex_id=ac.id
                LEFT JOIN portfolios p ON p.complex_id=ac.id
                WHERE {' AND '.join(cond)}
                GROUP BY ac.id
                ORDER BY portfolio_count DESC,apartment_type_count DESC,ac.id
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


def cluster_grid_summary(
    session: Session, *, north, south, east, west, cell_size: float
) -> list[dict[str, Any]]:
    """2026-08-25: 지도 클러스터 버블 숫자 정확도 보정용(2차 수정).
    처음엔 클러스터 하나당 요청 하나씩(cluster_portfolio_summary, bbox
    하나)이었는데, 화면 하나에 클러스터가 9~45개까지 생겨서 지도를
    켜거나 조금만 움직여도 요청이 그만큼 쏟아졌다 -- 기존 마커 로딩
    요청과 합쳐져 IP당 분당 300건 제한(RATE_LIMIT_REQUESTS_PER_MINUTE)
    에 쉽게 걸렸고, 한 번 걸리면 그 뒤 새로고침해도(직전 세션 요청이
    아직 60초 창 안에 남아있어) 기본 마커 조회 요청까지 같이 429로
    막혀서 "재접속해도 마커가 1분 넘게 안 뜬다"는 사고로 이어졌다
    (실사용자 리포트, V2.5.0_PLAN.md 2026-08-25 기록 참고).
    이 함수는 화면(bbox) 전체의 격자셀별 합계를 SQL GROUP BY 한 번으로
    모두 계산해서 돌려준다 -- 클러스터가 몇 개든 요청은 화면 하나당
    딱 1건으로 줄어든다. 격자 정의는 프론트 js/map-provider.js의
    clusterCell(zoom)과 반드시 같은 셀 크기를 써야 프론트 클러스터링과
    1:1로 맞는다(호출부에서 zoom으로 계산한 cell_size를 그대로 넘김)."""
    cond = ["ac.is_active=TRUE", *_type_visibility_conditions(session)]
    bbox_cond, params = _bbox_filters("ac", north, south, east, west, None, None)
    cond.extend(bbox_cond)
    clause = " AND ".join(cond)
    params["cell_size"] = cell_size
    rows = session.execute(
        text(
            f"""
            SELECT
                FLOOR(ac.latitude / :cell_size) AS lat_index,
                FLOOR(ac.longitude / :cell_size) AS lng_index,
                COUNT(*) AS complex_count,
                COALESCE(SUM(pc.portfolio_count), 0) AS total_portfolio_count
            FROM apartment_complexes ac
            CROSS JOIN LATERAL (
                SELECT COUNT(*) AS portfolio_count
                FROM portfolios p
                WHERE p.complex_id = ac.id
                  AND p.status = 'approved'
                  AND p.deleted_at IS NULL
            ) pc
            WHERE {clause}
            GROUP BY lat_index, lng_index
            HAVING COUNT(*) >= 2
            LIMIT 500
            """
        ),
        params,
    ).mappings().all()
    return [
        {
            "lat_index": int(row["lat_index"]),
            "lng_index": int(row["lng_index"]),
            "complex_count": int(row["complex_count"]),
            "total_portfolio_count": int(row["total_portfolio_count"]),
        }
        for row in rows
    ]


def search_map(session: Session, *, q: str, limit: int = 20):
    pattern = f"%{q}%"
    type_cond = _type_visibility_conditions(session)
    type_cond_sql = (" AND " + " AND ".join(type_cond)) if type_cond else ""
    rows = session.execute(
        text(
            f"""
            SELECT * FROM (
                SELECT
                    'complex'::text AS result_type,ac.id,ac.name,
                    ac.sido,ac.sigungu,ac.eupmyeondong,ac.latitude,ac.longitude,
                    COUNT(DISTINCT p.id) FILTER (
                        WHERE p.status='approved' AND p.deleted_at IS NULL
                    ) AS portfolio_count,
                    0 AS priority
                FROM apartment_complexes ac
                LEFT JOIN portfolios p ON p.complex_id=ac.id
                WHERE ac.is_active=TRUE
                  AND (
                      ac.name ILIKE :q OR ac.road_address ILIKE :q
                      OR ac.jibun_address ILIKE :q
                  )
                  {type_cond_sql}
                GROUP BY ac.id
                UNION ALL
                SELECT
                    'company'::text,c.id,c.name,c.sido,c.sigungu,c.eupmyeondong,
                    c.latitude,c.longitude,
                    COUNT(DISTINCT p.id) FILTER (
                        WHERE p.status='approved' AND p.deleted_at IS NULL
                    ),
                    1 AS priority
                FROM companies c
                LEFT JOIN portfolios p ON p.company_id=c.id
                WHERE c.status='active'
                  AND c.is_visible_on_map=TRUE
                  AND c.deleted_at IS NULL
                  AND c.name ILIKE :q
                GROUP BY c.id
            ) s
            ORDER BY priority,portfolio_count DESC,name
            LIMIT :limit
            """
        ),
        {"q": pattern, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def cluster_markers(
    markers: list[dict[str, Any]],
    *,
    marker_type: str,
    cell_degrees: Decimal,
) -> list[dict[str, Any]]:
    """Small deterministic server-side grid clustering for map viewport responses."""
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    cell = float(cell_degrees)
    for marker in markers:
        lat = float(marker["latitude"])
        lng = float(marker["longitude"])
        key = (int(lat // cell), int(lng // cell))
        buckets.setdefault(key, []).append(marker)

    result: list[dict[str, Any]] = []
    for (lat_cell, lng_cell), bucket in sorted(buckets.items()):
        if len(bucket) == 1:
            marker = bucket[0].copy()
            marker.update(
                item_type="marker",
                cluster_id=None,
                count=1,
                premium_count=1 if marker.get("is_premium") else 0,
            )
            result.append(marker)
            continue

        latitude = sum(Decimal(str(m["latitude"])) for m in bucket) / len(bucket)
        longitude = sum(Decimal(str(m["longitude"])) for m in bucket) / len(bucket)
        portfolio_count = sum(int(m.get("portfolio_count") or 0) for m in bucket)
        apartment_type_count = None
        if marker_type == "complex":
            apartment_type_count = sum(
                int(m.get("apartment_type_count") or 0) for m in bucket
            )
        premium_count = sum(1 for m in bucket if m.get("is_premium"))
        result.append(
            {
                "item_type": "cluster",
                "marker_type": marker_type,
                "cluster_id": f"{marker_type}:{lat_cell}:{lng_cell}",
                "id": None,
                "name": None,
                "latitude": latitude,
                "longitude": longitude,
                "count": len(bucket),
                "portfolio_count": portfolio_count,
                "apartment_type_count": apartment_type_count,
                "premium_count": premium_count,
                "consultation_available": None,
                "logo_path": None,
                "exposure_score": None,
                "map_priority": None,
                "is_premium": None,
                "marker_level": None,
            }
        )
    return result
