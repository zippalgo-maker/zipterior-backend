from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


PORTFOLIO_UPDATE_FIELDS = {
    "title",
    "summary",
    "description",
    "complex_id",
    "apartment_type_id",
    "construction_scope",
    "budget_min",
    "budget_max",
    "construction_days",
    "construction_date",
}


def list_company_portfolios(
    session: Session,
    *,
    company_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                p.title,
                p.summary,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name AS apartment_type_name,
                apt.pyeong_label,

                p.construction_scope,
                p.budget_min,
                p.budget_max,
                p.construction_days,
                p.construction_date,

                p.status,
                p.representative_image_id,
                pi.thumbnail_path
                    AS representative_thumbnail_path,

                p.view_count,
                p.like_count,
                p.comment_count,

                p.published_at,
                p.created_at,
                p.updated_at
            FROM portfolios AS p
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            WHERE p.company_id = :company_id
              AND p.deleted_at IS NULL
            ORDER BY p.updated_at DESC, p.id DESC
            """
        ),
        {"company_id": company_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def find_company_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                p.created_by_user_id,
                p.registration_source,

                p.title,
                p.summary,
                p.description,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name AS apartment_type_name,
                apt.pyeong_label,

                p.construction_scope,
                p.budget_min,
                p.budget_max,
                p.construction_days,
                p.construction_date,

                p.status,
                p.rejection_reason,
                p.representative_image_id,
                pi.thumbnail_path
                    AS representative_thumbnail_path,

                p.view_count,
                p.like_count,
                p.comment_count,

                p.published_at,
                p.created_at,
                p.updated_at
            FROM portfolios AS p
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            WHERE p.company_id = :company_id
              AND p.id = :portfolio_id
              AND p.deleted_at IS NULL
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_active_complex(
    session: Session,
    complex_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, name
            FROM apartment_complexes
            WHERE id = :complex_id
              AND is_active = TRUE
            LIMIT 1
            """
        ),
        {"complex_id": complex_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_apartment_type(
    session: Session,
    apartment_type_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                complex_id,
                type_name,
                pyeong_label
            FROM apartment_types
            WHERE id = :apartment_type_id
            LIMIT 1
            """
        ),
        {"apartment_type_id": apartment_type_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def create_portfolio(
    session: Session,
    *,
    company_id: int,
    created_by_user_id: int,
    values: dict[str, Any],
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO portfolios (
                    company_id,
                    complex_id,
                    apartment_type_id,
                    created_by_user_id,
                    registration_source,
                    title,
                    summary,
                    description,
                    construction_scope,
                    budget_min,
                    budget_max,
                    construction_days,
                    construction_date,
                    status
                )
                VALUES (
                    :company_id,
                    :complex_id,
                    :apartment_type_id,
                    :created_by_user_id,
                    'company',
                    :title,
                    :summary,
                    :description,
                    :construction_scope,
                    :budget_min,
                    :budget_max,
                    :construction_days,
                    :construction_date,
                    'draft'
                )
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "created_by_user_id": created_by_user_id,
                "complex_id": values.get("complex_id"),
                "apartment_type_id": values.get(
                    "apartment_type_id"
                ),
                "title": values["title"],
                "summary": values.get("summary"),
                "description": values.get("description"),
                "construction_scope": values.get(
                    "construction_scope"
                ),
                "budget_min": values.get("budget_min"),
                "budget_max": values.get("budget_max"),
                "construction_days": values.get(
                    "construction_days"
                ),
                "construction_date": values.get(
                    "construction_date"
                ),
            },
        ).scalar_one()
    )


def update_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
    changes: dict[str, Any],
) -> bool:
    safe_changes = {
        key: value
        for key, value in changes.items()
        if key in PORTFOLIO_UPDATE_FIELDS
    }

    if not safe_changes:
        return False

    assignments = [
        f"{column_name} = :{column_name}"
        for column_name in safe_changes
    ]
    assignments.extend(
        [
            "rejection_reason = NULL",
            "updated_at = NOW()",
        ]
    )

    result = session.execute(
        text(
            f"""
            UPDATE portfolios
            SET {", ".join(assignments)}
            WHERE id = :portfolio_id
              AND company_id = :company_id
              AND deleted_at IS NULL
            """
        ),
        {
            **safe_changes,
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def submit_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'pending',
                rejection_reason = NULL,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND company_id = :company_id
              AND status IN ('draft', 'rejected')
              AND deleted_at IS NULL
            """
        ),
        {
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def hide_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
) -> bool:
    """v2.5.0: 업체가 자기 승인된 포트폴리오를 스스로 비공개(hidden)로
    돌린다 -- 재검수 없이 approved -> hidden만 허용."""
    result = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'hidden',
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND company_id = :company_id
              AND status = 'approved'
              AND deleted_at IS NULL
            """
        ),
        {
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def show_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
) -> bool:
    """v2.5.0: 업체가 스스로 숨긴 포트폴리오를 다시 공개한다 -- 이미 한 번
    승인됐던 것이라 hidden -> approved만 허용, 관리자 재검수는 거치지 않는다."""
    result = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'approved',
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND company_id = :company_id
              AND status = 'hidden'
              AND deleted_at IS NULL
            """
        ),
        {
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def soft_delete_portfolio(
    session: Session,
    *,
    company_id: int,
    portfolio_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolios
            SET deleted_at = NOW(),
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND company_id = :company_id
              AND status IN ('draft', 'rejected', 'hidden')
              AND deleted_at IS NULL
            """
        ),
        {
            "company_id": company_id,
            "portfolio_id": portfolio_id,
        },
    )

    return bool(result.rowcount)


def list_portfolio_images(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                portfolio_id,
                portfolio_space_id,
                room_code,
                original_filename,
                original_mime_type,
                original_size_bytes,
                original_width,
                original_height,
                large_path,
                large_size_bytes,
                large_width,
                large_height,
                medium_path,
                medium_size_bytes,
                medium_width,
                medium_height,
                thumbnail_path,
                thumbnail_size_bytes,
                thumbnail_width,
                thumbnail_height,
                sort_order,
                is_representative,
                processing_status,
                processing_error,
                description,
                created_at
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
            ORDER BY
                is_representative DESC,
                sort_order,
                id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def find_portfolio_image(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                portfolio_id,
                portfolio_space_id,
                room_code,
                original_filename,
                stored_filename,
                original_mime_type,
                original_size_bytes,
                original_width,
                original_height,
                large_path,
                large_size_bytes,
                large_width,
                large_height,
                medium_path,
                medium_size_bytes,
                medium_width,
                medium_height,
                thumbnail_path,
                thumbnail_size_bytes,
                thumbnail_width,
                thumbnail_height,
                sort_order,
                is_representative,
                processing_status,
                processing_error,
                created_at
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
              AND id = :image_id
            LIMIT 1
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def count_portfolio_images(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM portfolio_images
                WHERE portfolio_id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def next_portfolio_image_sort_order(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COALESCE(MAX(sort_order), -1) + 1
                FROM portfolio_images
                WHERE portfolio_id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )


def create_portfolio_image(
    session: Session,
    *,
    portfolio_id: int,
    room_code: str,
    original_filename: str,
    stored_filename: str,
    original_mime_type: str,
    original_size_bytes: int,
    original_width: int,
    original_height: int,
    large_path: str,
    large_size_bytes: int,
    large_width: int,
    large_height: int,
    medium_path: str,
    medium_size_bytes: int,
    medium_width: int,
    medium_height: int,
    thumbnail_path: str,
    thumbnail_size_bytes: int,
    thumbnail_width: int,
    thumbnail_height: int,
    sort_order: int,
    is_representative: bool,
    description: str | None = None,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO portfolio_images (
                    portfolio_id,
                    room_code,
                    original_filename,
                    stored_filename,
                    original_mime_type,
                    original_size_bytes,
                    original_width,
                    original_height,
                    large_path,
                    large_size_bytes,
                    large_width,
                    large_height,
                    medium_path,
                    medium_size_bytes,
                    medium_width,
                    medium_height,
                    thumbnail_path,
                    thumbnail_size_bytes,
                    thumbnail_width,
                    thumbnail_height,
                    sort_order,
                    is_representative,
                    description,
                    processing_status
                )
                VALUES (
                    :portfolio_id,
                    :room_code,
                    :original_filename,
                    CAST(:stored_filename AS uuid),
                    :original_mime_type,
                    :original_size_bytes,
                    :original_width,
                    :original_height,
                    :large_path,
                    :large_size_bytes,
                    :large_width,
                    :large_height,
                    :medium_path,
                    :medium_size_bytes,
                    :medium_width,
                    :medium_height,
                    :thumbnail_path,
                    :thumbnail_size_bytes,
                    :thumbnail_width,
                    :thumbnail_height,
                    :sort_order,
                    :is_representative,
                    :description,
                    'completed'
                )
                RETURNING id
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "room_code": room_code,
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "original_mime_type": original_mime_type,
                "original_size_bytes": original_size_bytes,
                "original_width": original_width,
                "original_height": original_height,
                "large_path": large_path,
                "large_size_bytes": large_size_bytes,
                "large_width": large_width,
                "large_height": large_height,
                "medium_path": medium_path,
                "medium_size_bytes": medium_size_bytes,
                "medium_width": medium_width,
                "medium_height": medium_height,
                "thumbnail_path": thumbnail_path,
                "thumbnail_size_bytes": thumbnail_size_bytes,
                "thumbnail_width": thumbnail_width,
                "thumbnail_height": thumbnail_height,
                "sort_order": sort_order,
                "is_representative": is_representative,
                "description": description,
            },
        ).scalar_one()
    )


def update_portfolio_image_metadata(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
    changes: dict[str, Any],
) -> bool:
    allowed_fields = {
        "room_code",
        "sort_order",
    }

    safe_changes = {
        key: value
        for key, value in changes.items()
        if key in allowed_fields
    }

    if not safe_changes:
        return False

    assignments = [
        f"{field} = :{field}"
        for field in safe_changes
    ]

    result = session.execute(
        text(
            f"""
            UPDATE portfolio_images
            SET {", ".join(assignments)}
            WHERE portfolio_id = :portfolio_id
              AND id = :image_id
            """
        ),
        {
            **safe_changes,
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    )

    return bool(result.rowcount)


def clear_portfolio_representative_images(
    session: Session,
    *,
    portfolio_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE portfolio_images
            SET is_representative = FALSE
            WHERE portfolio_id = :portfolio_id
              AND is_representative = TRUE
            """
        ),
        {"portfolio_id": portfolio_id},
    )


def set_portfolio_representative_image(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolio_images
            SET is_representative = TRUE
            WHERE portfolio_id = :portfolio_id
              AND id = :image_id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    )

    if not result.rowcount:
        return False

    session.execute(
        text(
            """
            UPDATE portfolios
            SET representative_image_id = :image_id,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND deleted_at IS NULL
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    )

    return True


def clear_portfolio_representative_image_reference(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE portfolios
            SET representative_image_id = NULL,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND representative_image_id = :image_id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    )


def delete_portfolio_image(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
) -> bool:
    deleted_id = session.execute(
        text(
            """
            DELETE FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
              AND id = :image_id
            RETURNING id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
        },
    ).scalar_one_or_none()

    return deleted_id is not None


def promote_first_portfolio_image(
    session: Session,
    *,
    portfolio_id: int,
) -> int | None:
    image_id = session.execute(
        text(
            """
            SELECT id
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
            ORDER BY sort_order, id
            LIMIT 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).scalar_one_or_none()

    if image_id is None:
        return None

    clear_portfolio_representative_images(
        session,
        portfolio_id=portfolio_id,
    )

    set_portfolio_representative_image(
        session,
        portfolio_id=portfolio_id,
        image_id=image_id,
    )

    return int(image_id)


def match_complex_search_items(
    session: Session,
    items: list[dict],
) -> list[dict]:
    if not items:
        return []

    rows = session.execute(
        text(
            """
            SELECT
                id,
                name,
                road_address,
                jibun_address,
                latitude,
                longitude
            FROM apartment_complexes
            """
        )
    ).mappings().all()

    complexes = [dict(row) for row in rows]

    def normalize(value):
        if value is None:
            return ""
        return "".join(str(value).lower().split()).replace("-", "")

    def distance_score(a, b):
        try:
            return abs(float(a) - float(b))
        except (TypeError, ValueError):
            return 999

    result = []

    for item in items:
        name = item.get("name") or ""
        road = item.get("road_address") or ""
        jibun = item.get("jibun_address") or ""
        lat = item.get("latitude")
        lon = item.get("longitude")

        matched = None

        # 1차: 도로명/지번 주소가 정확히 일치하면 같은 단지로 판단
        for complex_row in complexes:
            if road and complex_row.get("road_address"):
                if normalize(road) == normalize(complex_row["road_address"]):
                    matched = complex_row
                    break

            if jibun and complex_row.get("jibun_address"):
                if normalize(jibun) == normalize(complex_row["jibun_address"]):
                    matched = complex_row
                    break

        # 2차: 이름 + 좌표가 가까운 경우
        if matched is None:
            for complex_row in complexes:
                if normalize(name) != normalize(complex_row.get("name")):
                    continue

                if (
                    lat is not None
                    and lon is not None
                    and complex_row.get("latitude") is not None
                    and complex_row.get("longitude") is not None
                ):
                    if (
                        distance_score(lat, complex_row["latitude"]) <= 0.002
                        and distance_score(lon, complex_row["longitude"]) <= 0.002
                    ):
                        matched = complex_row
                        break

        result.append(
            {
                **item,
                "registered": matched is not None,
                "complex_id": matched["id"] if matched else None,
            }
        )

    return result


def upsert_complex_location(
    session: Session,
    *,
    name: str,
    road_address: str | None,
    jibun_address: str | None,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    address_key = road_address or jibun_address or ""
    row = session.execute(
        text(
            """
            SELECT id, name, road_address, jibun_address, latitude, longitude
            FROM apartment_complexes
            WHERE is_active = TRUE
              AND (
                    (road_address IS NOT NULL AND road_address = :address_key)
                 OR (jibun_address IS NOT NULL AND jibun_address = :address_key)
                 OR (name = :name AND ABS(latitude - :latitude) < 0.00015 AND ABS(longitude - :longitude) < 0.00015)
              )
            ORDER BY id
            LIMIT 1
            """
        ),
        {"name": name, "address_key": address_key, "latitude": latitude, "longitude": longitude},
    ).mappings().one_or_none()
    if row:
        return dict(row)

    # Kakao 선택값으로 최소 단지 마스터를 생성한다. 상세 행정정보는 후속 정제 가능.
    created = session.execute(
        text(
            """
            INSERT INTO apartment_complexes (
                name, road_address, jibun_address, latitude, longitude, is_active
            ) VALUES (
                :name, :road_address, :jibun_address, :latitude, :longitude, TRUE
            )
            RETURNING id, name, road_address, jibun_address, latitude, longitude
            """
        ),
        {"name": name, "road_address": road_address, "jibun_address": jibun_address, "latitude": latitude, "longitude": longitude},
    ).mappings().one()
    return dict(created)

def create_complex_registration_request(
    session: Session,
    *,
    company_id: int,
    name: str,
    road_address: str | None,
    jibun_address: str | None,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    existing = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                requested_name,
                requested_road_address,
                requested_jibun_address,
                requested_latitude,
                requested_longitude,
                status,
                completed_complex_id,
                created_at,
                updated_at,
                completed_at
            FROM complex_registration_requests
            WHERE company_id = :company_id
              AND status = 'requested'
              AND (
                    (
                        requested_road_address IS NOT NULL
                        AND requested_road_address = :road_address
                    )
                    OR (
                        requested_jibun_address IS NOT NULL
                        AND requested_jibun_address = :jibun_address
                    )
                    OR (
                        requested_name = :name
                        AND requested_latitude IS NOT NULL
                        AND requested_longitude IS NOT NULL
                        AND ABS(requested_latitude - :latitude) < 0.00015
                        AND ABS(requested_longitude - :longitude) < 0.00015
                    )
              )
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "name": name,
            "road_address": road_address,
            "jibun_address": jibun_address,
            "latitude": latitude,
            "longitude": longitude,
        },
    ).mappings().one_or_none()

    if existing:
        return {
            **dict(existing),
            "already_requested": True,
        }

    row = session.execute(
        text(
            """
            INSERT INTO complex_registration_requests (
                company_id,
                requested_name,
                requested_road_address,
                requested_jibun_address,
                requested_latitude,
                requested_longitude,
                status
            )
            VALUES (
                :company_id,
                :name,
                :road_address,
                :jibun_address,
                :latitude,
                :longitude,
                'requested'
            )
            RETURNING
                id,
                company_id,
                requested_name,
                requested_road_address,
                requested_jibun_address,
                requested_latitude,
                requested_longitude,
                status,
                completed_complex_id,
                created_at,
                updated_at,
                completed_at
            """
        ),
        {
            "company_id": company_id,
            "name": name,
            "road_address": road_address,
            "jibun_address": jibun_address,
            "latitude": latitude,
            "longitude": longitude,
        },
    ).mappings().one()

    return {
        **dict(row),
        "already_requested": False,
    }


# ============================================================
# v2.1.8 Structured portfolio spaces
# ============================================================

def list_portfolio_spaces(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                ps.id,
                ps.portfolio_id,
                ps.space_code,
                ps.space_name,
                ps.space_number,
                ps.description,
                ps.sort_order,
                ps.created_at,
                ps.updated_at,
                COUNT(pi.id)::int AS image_count
            FROM portfolio_spaces ps
            LEFT JOIN portfolio_images pi
              ON pi.portfolio_space_id = ps.id
             AND pi.portfolio_id = ps.portfolio_id
            WHERE ps.portfolio_id = :portfolio_id
            GROUP BY
                ps.id,
                ps.portfolio_id,
                ps.space_code,
                ps.space_name,
                ps.space_number,
                ps.description,
                ps.sort_order,
                ps.created_at,
                ps.updated_at
            ORDER BY
                ps.sort_order,
                ps.space_code,
                ps.space_number,
                ps.id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def find_portfolio_space(
    session: Session,
    *,
    portfolio_id: int,
    space_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                ps.id,
                ps.portfolio_id,
                ps.space_code,
                ps.space_name,
                ps.space_number,
                ps.description,
                ps.sort_order,
                ps.created_at,
                ps.updated_at,
                COUNT(pi.id)::int AS image_count
            FROM portfolio_spaces ps
            LEFT JOIN portfolio_images pi
              ON pi.portfolio_space_id = ps.id
             AND pi.portfolio_id = ps.portfolio_id
            WHERE ps.portfolio_id = :portfolio_id
              AND ps.id = :space_id
            GROUP BY
                ps.id,
                ps.portfolio_id,
                ps.space_code,
                ps.space_name,
                ps.space_number,
                ps.description,
                ps.sort_order,
                ps.created_at,
                ps.updated_at
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "space_id": space_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def next_portfolio_space_number(
    session: Session,
    *,
    portfolio_id: int,
    space_code: str,
) -> int:
    value = session.execute(
        text(
            """
            SELECT COALESCE(MAX(space_number), 0) + 1
            FROM portfolio_spaces
            WHERE portfolio_id = :portfolio_id
              AND space_code = :space_code
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "space_code": space_code,
        },
    ).scalar_one()

    return int(value)


def next_portfolio_space_sort_order(
    session: Session,
    *,
    portfolio_id: int,
) -> int:
    value = session.execute(
        text(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM portfolio_spaces
            WHERE portfolio_id = :portfolio_id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).scalar_one()

    return int(value)


def create_portfolio_space(
    session: Session,
    *,
    portfolio_id: int,
    space_code: str,
    space_name: str,
    space_number: int,
    description: str | None,
    sort_order: int,
) -> int:
    space_id = session.execute(
        text(
            """
            INSERT INTO portfolio_spaces (
                portfolio_id,
                space_code,
                space_name,
                space_number,
                description,
                sort_order
            )
            VALUES (
                :portfolio_id,
                :space_code,
                :space_name,
                :space_number,
                :description,
                :sort_order
            )
            RETURNING id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "space_code": space_code,
            "space_name": space_name,
            "space_number": space_number,
            "description": description,
            "sort_order": sort_order,
        },
    ).scalar_one()

    return int(space_id)


def update_portfolio_space(
    session: Session,
    *,
    portfolio_id: int,
    space_id: int,
    changes: dict[str, Any],
) -> bool:
    allowed = {
        "space_name",
        "description",
        "sort_order",
    }

    updates = {
        key: value
        for key, value in changes.items()
        if key in allowed
    }

    if not updates:
        return False

    set_parts = []
    params: dict[str, Any] = {
        "portfolio_id": portfolio_id,
        "space_id": space_id,
    }

    for key, value in updates.items():
        set_parts.append(f"{key} = :{key}")
        params[key] = value

    set_parts.append("updated_at = NOW()")

    result = session.execute(
        text(
            f"""
            UPDATE portfolio_spaces
            SET {", ".join(set_parts)}
            WHERE portfolio_id = :portfolio_id
              AND id = :space_id
            """
        ),
        params,
    )

    return bool(result.rowcount)


def count_portfolio_space_images(
    session: Session,
    *,
    portfolio_id: int,
    space_id: int,
) -> int:
    value = session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
              AND portfolio_space_id = :space_id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "space_id": space_id,
        },
    ).scalar_one()

    return int(value)


def delete_portfolio_space(
    session: Session,
    *,
    portfolio_id: int,
    space_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            DELETE FROM portfolio_spaces
            WHERE portfolio_id = :portfolio_id
              AND id = :space_id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "space_id": space_id,
        },
    )

    return bool(result.rowcount)


def set_portfolio_image_space(
    session: Session,
    *,
    portfolio_id: int,
    image_id: int,
    portfolio_space_id: int | None,
) -> bool:
    result = session.execute(
        text(
            """
            UPDATE portfolio_images
            SET portfolio_space_id = :portfolio_space_id
            WHERE portfolio_id = :portfolio_id
              AND id = :image_id
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "image_id": image_id,
            "portfolio_space_id": portfolio_space_id,
        },
    )

    return bool(result.rowcount)

