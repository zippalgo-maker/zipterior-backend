from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


NORMALIZED_COMPLEX_MATCH = """
    regexp_replace(
        regexp_replace(lower(ac.name), '\\([^)]*\\)|아파트|주상복합|오피스텔', '', 'g'),
        '[^0-9a-z가-힣]', '', 'g'
    ) = regexp_replace(
        regexp_replace(lower(:name), '\\([^)]*\\)|아파트|주상복합|오피스텔', '', 'g'),
        '[^0-9a-z가-힣]', '', 'g'
    )
    AND regexp_replace(
        replace(lower(coalesce(ac.road_address, '')), '경기도', '경기'),
        '[^0-9a-z가-힣]', '', 'g'
    ) = regexp_replace(
        replace(lower(coalesce(:road_address, '')), '경기도', '경기'),
        '[^0-9a-z가-힣]', '', 'g'
    )
"""


def find_duplicate_complex(
    session: Session,
    *,
    name: str,
    road_address: str | None,
    exclude_id: int | None = None,
) -> dict[str, Any] | None:
    """서비스 사전 안내와 DB 고유 인덱스가 같은 정규화 기준을 사용한다."""
    if not road_address:
        return None
    row = session.execute(
        text(
            f"""
            SELECT ac.id, ac.name, ac.road_address
            FROM apartment_complexes ac
            WHERE ac.is_active = TRUE
              AND ({NORMALIZED_COMPLEX_MATCH})
              AND (
                  CAST(:exclude_id AS BIGINT) IS NULL
                  OR ac.id <> CAST(:exclude_id AS BIGINT)
              )
            ORDER BY ac.id
            LIMIT 1
            """
        ),
        {
            "name": name,
            "road_address": road_address,
            "exclude_id": exclude_id,
        },
    ).mappings().one_or_none()
    return dict(row) if row else None

def list_complexes(
    session: Session,
    *,
    q: str | None = None,
    sido: str | None = None,
    sigungu: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if q:
        conditions.append(
            "(ac.name ILIKE :q OR COALESCE(ac.road_address,'') ILIKE :q "
            "OR COALESCE(ac.jibun_address,'') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if sido:
        conditions.append("ac.sido = :sido")
        params["sido"] = sido

    if sigungu:
        conditions.append("ac.sigungu = :sigungu")
        params["sigungu"] = sigungu

    rows = session.execute(
        text(
            f"""
            SELECT ac.id, ac.name, ac.sido, ac.sigungu, ac.eupmyeondong,
                   ac.road_address, ac.jibun_address,
                   ac.latitude, ac.longitude, ac.completion_year,
                   ac.household_count, ac.building_count,
                   ac.parking_count, ac.heating_type, ac.builder_name,
                   ac.complex_type,
                   ac.representative_image_path,
                   ac.representative_thumbnail_path,
                   ac.is_active,
                   COUNT(DISTINCT apt.id) AS apartment_type_count,
                   COUNT(DISTINCT p.id) FILTER (
                       WHERE p.status='approved' AND p.deleted_at IS NULL
                   ) AS portfolio_count
            FROM apartment_complexes ac
            LEFT JOIN apartment_types apt ON apt.complex_id=ac.id
            LEFT JOIN portfolios p ON p.complex_id=ac.id
            WHERE {' AND '.join(conditions)}
            GROUP BY ac.id
            ORDER BY ac.name, ac.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]

def count_complexes(
    session: Session,
    *,
    q: str | None = None,
    sido: str | None = None,
    sigungu: str | None = None,
) -> int:
    conditions = ["1=1"]
    params: dict[str, Any] = {}

    if q:
        conditions.append(
            "(ac.name ILIKE :q OR COALESCE(ac.road_address,'') ILIKE :q "
            "OR COALESCE(ac.jibun_address,'') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if sido:
        conditions.append("ac.sido = :sido")
        params["sido"] = sido

    if sigungu:
        conditions.append("ac.sigungu = :sigungu")
        params["sigungu"] = sigungu

    return int(
        session.execute(
            text(
                f"SELECT COUNT(*) FROM apartment_complexes ac "
                f"WHERE {' AND '.join(conditions)}"
            ),
            params,
        ).scalar_one()
    )

def find_complex(
    session: Session,
    complex_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                ac.id, ac.name, ac.sido, ac.sigungu, ac.eupmyeondong,
                ac.road_address, ac.jibun_address,
                ac.latitude, ac.longitude,
                ac.completion_year, ac.household_count,
                ac.building_count, ac.parking_count,
                ac.heating_type, ac.builder_name,
                ac.complex_type,
                ac.representative_image_path,
                ac.representative_thumbnail_path,
                ac.is_active,
                COUNT(DISTINCT apt.id) AS apartment_type_count,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status='approved' AND p.deleted_at IS NULL
                ) AS portfolio_count
            FROM apartment_complexes ac
            LEFT JOIN apartment_types apt ON apt.complex_id=ac.id
            LEFT JOIN portfolios p ON p.complex_id=ac.id
            WHERE ac.id=:id
            GROUP BY ac.id
            """
        ),
        {"id": complex_id},
    ).mappings().one_or_none()

    return dict(row) if row else None

def list_apartment_types(
    session: Session,
    *,
    complex_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                apt.id,
                apt.complex_id,
                apt.type_name,
                apt.supply_area_m2,
                apt.exclusive_area_m2,
                apt.pyeong_label,
                apt.room_count,
                apt.bathroom_count,
                apt.floor_plan_path,
                apt.has_basic_layout,
                apt.has_expanded_layout,
                apt.sort_order,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE p.status != 'hidden'
                      AND p.deleted_at IS NULL
                ) AS portfolio_count
            FROM apartment_types apt
            LEFT JOIN portfolios p
                ON p.apartment_type_id = apt.id
            WHERE apt.complex_id = :complex_id
            GROUP BY apt.id
            ORDER BY apt.sort_order, apt.id
            """
        ),
        {"complex_id": complex_id},
    ).mappings().all()

    return [dict(row) for row in rows]

def count_apartment_types(
    session: Session,
    *,
    complex_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM apartment_types
                WHERE complex_id = :complex_id
                """
            ),
            {"complex_id": complex_id},
        ).scalar_one()
    )


def find_apartment_type(
    session: Session,
    *,
    complex_id: int,
    type_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                complex_id,
                type_name,
                supply_area_m2,
                exclusive_area_m2,
                pyeong_label,
                room_count,
                bathroom_count,
                floor_plan_path,
                has_basic_layout,
                has_expanded_layout,
                sort_order
            FROM apartment_types
            WHERE id=:type_id
              AND complex_id=:complex_id
            LIMIT 1
            """
        ),
        {
            "type_id": type_id,
            "complex_id": complex_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None

def create_complex(
    session: Session,
    *,
    values: dict[str, Any],
) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO apartment_complexes (
                name, sido, sigungu, eupmyeondong,
                road_address, jibun_address,
                latitude, longitude,
                completion_year, household_count,
                building_count, parking_count,
                heating_type, builder_name, complex_type, is_active
            )
            VALUES (
                :name, :sido, :sigungu, :eupmyeondong,
                :road_address, :jibun_address,
                :latitude, :longitude,
                :completion_year, :household_count,
                :building_count, :parking_count,
                :heating_type, :builder_name, :complex_type, TRUE
            )
            RETURNING id
            """
        ),
        # v2.5.1: 시군구 자동수집이 아닌 기존 수동 등록 경로는 complex_type을
        # 안 넘기므로(values에 키 자체가 없음) 기본값 None(미분류)으로 채운다.
        {**values, "complex_type": values.get("complex_type")},
    ).scalar_one()

    return int(row)

def update_complex(
    session: Session,
    *,
    complex_id: int,
    values: dict[str, Any],
) -> bool:
    allowed = {
        "name", "sido", "sigungu", "eupmyeondong",
        "road_address", "jibun_address",
        "latitude", "longitude", "completion_year",
        "household_count", "building_count", "parking_count",
        "heating_type", "builder_name", "complex_type", "is_active",
    }

    changes = {
        key: value
        for key, value in values.items()
        if key in allowed
    }

    if not changes:
        return False

    assignments = [f"{key}=:{key}" for key in changes]
    changes["complex_id"] = complex_id

    result = session.execute(
        text(
            f"""
            UPDATE apartment_complexes
            SET {', '.join(assignments)},
                updated_at=NOW()
            WHERE id=:complex_id
            """
        ),
        changes,
    )

    return result.rowcount > 0

def create_apartment_type(
    session: Session,
    *,
    complex_id: int,
    values: dict[str, Any],
) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO apartment_types (
                complex_id, type_name,
                supply_area_m2, exclusive_area_m2,
                pyeong_label, room_count,
                bathroom_count, floor_plan_path,
                has_basic_layout, has_expanded_layout,
                sort_order
            )
            VALUES (
                :complex_id, :type_name,
                :supply_area_m2, :exclusive_area_m2,
                :pyeong_label, :room_count,
                :bathroom_count, :floor_plan_path,
                :has_basic_layout, :has_expanded_layout,
                :sort_order
            )
            RETURNING id
            """
        ),
        {
            "complex_id": complex_id,
            **values,
        },
    ).scalar_one()

    return int(row)

def update_apartment_type(
    session: Session,
    *,
    complex_id: int,
    type_id: int,
    values: dict[str, Any],
) -> bool:
    allowed = {
        "type_name", "supply_area_m2", "exclusive_area_m2",
        "pyeong_label", "room_count", "bathroom_count",
        "floor_plan_path", "has_basic_layout", "has_expanded_layout",
        "sort_order",
    }

    changes = {
        key: value
        for key, value in values.items()
        if key in allowed
    }

    if not changes:
        return False

    assignments = [f"{key}=:{key}" for key in changes]

    changes["complex_id"] = complex_id
    changes["type_id"] = type_id

    result = session.execute(
        text(
            f"""
            UPDATE apartment_types
            SET {', '.join(assignments)}
            WHERE id=:type_id
              AND complex_id=:complex_id
            """
        ),
        changes,
    )

    return result.rowcount > 0

def count_type_references(
    session: Session,
    *,
    type_id: int,
) -> dict[str, int]:
    portfolio_count = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM portfolios
                WHERE apartment_type_id=:type_id
                  AND deleted_at IS NULL
                """
            ),
            {"type_id": type_id},
        ).scalar_one()
    )

    estimate_count = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM estimate_requests
                WHERE apartment_type_id=:type_id
                """
            ),
            {"type_id": type_id},
        ).scalar_one()
    )

    return {
        "portfolio_count": portfolio_count,
        "estimate_count": estimate_count,
    }

def delete_apartment_type(
    session: Session,
    *,
    complex_id: int,
    type_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            DELETE FROM apartment_types
            WHERE id=:type_id
              AND complex_id=:complex_id
            """
        ),
        {
            "type_id": type_id,
            "complex_id": complex_id,
        },
    )

    return result.rowcount > 0

def list_complex_registration_requests(
    session: Session,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions = ["1=1"]
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if status in {"requested", "completed"}:
        conditions.append("crr.status = :status")
        params["status"] = status

    if q:
        conditions.append(
            "(crr.requested_name ILIKE :q "
            "OR COALESCE(crr.requested_road_address, '') ILIKE :q "
            "OR COALESCE(crr.requested_jibun_address, '') ILIKE :q "
            "OR COALESCE(c.name, '') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    rows = session.execute(
        text(
            f"""
            SELECT
                crr.id,
                crr.company_id,
                c.name AS company_name,
                crr.requested_name,
                crr.requested_road_address,
                crr.requested_jibun_address,
                crr.requested_latitude,
                crr.requested_longitude,
                crr.status,
                crr.completed_complex_id,
                ac.name AS completed_complex_name,
                crr.created_at,
                crr.updated_at,
                crr.completed_at
            FROM complex_registration_requests crr
            LEFT JOIN companies c
              ON c.id = crr.company_id
            LEFT JOIN apartment_complexes ac
              ON ac.id = crr.completed_complex_id
            WHERE {' AND '.join(conditions)}
            ORDER BY
                CASE WHEN crr.status = 'requested' THEN 0 ELSE 1 END,
                crr.created_at DESC,
                crr.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


def count_complex_registration_requests(
    session: Session,
    *,
    status: str | None = None,
    q: str | None = None,
) -> int:
    conditions = ["1=1"]
    params: dict[str, Any] = {}

    if status in {"requested", "completed"}:
        conditions.append("crr.status = :status")
        params["status"] = status

    if q:
        conditions.append(
            "(crr.requested_name ILIKE :q "
            "OR COALESCE(crr.requested_road_address, '') ILIKE :q "
            "OR COALESCE(crr.requested_jibun_address, '') ILIKE :q "
            "OR COALESCE(c.name, '') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    return int(
        session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM complex_registration_requests crr
                LEFT JOIN companies c
                  ON c.id = crr.company_id
                WHERE {' AND '.join(conditions)}
                """
            ),
            params,
        ).scalar_one()
    )

def complete_complex_registration_request(
    session: Session,
    *,
    request_id: int,
    complex_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE complex_registration_requests
            SET status = 'completed',
                completed_complex_id = :complex_id,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = :request_id
              AND status = 'requested'
            """
        ),
        {"request_id": request_id, "complex_id": complex_id},
    )
    return result.rowcount > 0


def list_complex_images(
    session: Session,
    *,
    complex_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT id, complex_id, image_path, thumbnail_path,
                   width, height, size_bytes, sort_order, is_representative
            FROM apartment_complex_images
            WHERE complex_id = :complex_id
            ORDER BY is_representative DESC, sort_order, id
            """
        ),
        {"complex_id": complex_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def find_complex_image(
    session: Session,
    *,
    complex_id: int,
    image_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, complex_id, image_path, thumbnail_path,
                   width, height, size_bytes, sort_order, is_representative
            FROM apartment_complex_images
            WHERE id = :image_id AND complex_id = :complex_id
            """
        ),
        {"complex_id": complex_id, "image_id": image_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def create_complex_image(
    session: Session,
    *,
    complex_id: int,
    values: dict[str, Any],
) -> int:
    """첫 사진만 자동 대표로 지정하며 이후 대표 변경은 명시적 API가 담당한다."""
    row = session.execute(
        text(
            """
            INSERT INTO apartment_complex_images (
                complex_id, image_path, thumbnail_path,
                width, height, size_bytes, sort_order, is_representative
            )
            SELECT :complex_id, :image_path, :thumbnail_path,
                   :width, :height, :size_bytes,
                   COALESCE(MAX(sort_order) + 1, 0),
                   COUNT(*) = 0
            FROM apartment_complex_images
            WHERE complex_id = :complex_id
            RETURNING id
            """
        ),
        {"complex_id": complex_id, **values},
    ).scalar_one()
    return int(row)


def set_representative_complex_image(
    session: Session,
    *,
    complex_id: int,
    image_id: int,
) -> bool:
    image = find_complex_image(
        session, complex_id=complex_id, image_id=image_id
    )
    if image is None:
        return False
    session.execute(
        text(
            """
            UPDATE apartment_complex_images
            SET is_representative = FALSE, updated_at = NOW()
            WHERE complex_id = :complex_id AND is_representative = TRUE
            """
        ),
        {"complex_id": complex_id},
    )
    session.execute(
        text(
            """
            UPDATE apartment_complex_images
            SET is_representative = TRUE, updated_at = NOW()
            WHERE id = :image_id AND complex_id = :complex_id
            """
        ),
        {"complex_id": complex_id, "image_id": image_id},
    )
    session.execute(
        text(
            """
            UPDATE apartment_complexes
            SET representative_image_path = :image_path,
                representative_thumbnail_path = :thumbnail_path,
                updated_at = NOW()
            WHERE id = :complex_id
            """
        ),
        {
            "complex_id": complex_id,
            "image_path": image["image_path"],
            "thumbnail_path": image["thumbnail_path"],
        },
    )
    return True


def delete_complex_image(
    session: Session,
    *,
    complex_id: int,
    image_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            DELETE FROM apartment_complex_images
            WHERE id = :image_id AND complex_id = :complex_id
            """
        ),
        {"complex_id": complex_id, "image_id": image_id},
    )
    return result.rowcount > 0


def select_first_complex_image_id(
    session: Session,
    *,
    complex_id: int,
) -> int | None:
    value = session.execute(
        text(
            """
            SELECT id FROM apartment_complex_images
            WHERE complex_id = :complex_id
            ORDER BY sort_order, id LIMIT 1
            """
        ),
        {"complex_id": complex_id},
    ).scalar_one_or_none()
    return int(value) if value is not None else None


def clear_representative_complex_image(
    session: Session,
    *,
    complex_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE apartment_complexes
            SET representative_image_path = NULL,
                representative_thumbnail_path = NULL,
                updated_at = NOW()
            WHERE id = :complex_id
            """
        ),
        {"complex_id": complex_id},
    )
