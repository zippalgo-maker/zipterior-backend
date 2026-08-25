from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_pending_portfolios(
    session: Session,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                c.name AS company_name,

                p.title,
                p.summary,
                p.description,

                p.complex_id,
                ac.name AS complex_name,

                p.apartment_type_id,
                apt.type_name AS apartment_type_name,
                apt.pyeong_label,

                p.representative_image_id,
                pi.thumbnail_path
                    AS representative_thumbnail_path,

                p.status,
                p.created_by_user_id,
                p.updated_at AS submitted_at
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN apartment_types AS apt
              ON apt.id = p.apartment_type_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            WHERE p.status = 'pending'
              AND p.deleted_at IS NULL
            ORDER BY p.updated_at, p.id
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


# 2026-08-22: 관리자 "포트폴리오 관리" 화면을 진짜 서버 페이지네이션으로
# 바꾸면서(기존엔 limit만 200->500->1000으로 올리는 임시방편이었는데,
# 데이터가 9천~2만 건까지 늘어날 예정이라 "다 불러온 뒤 클라이언트에서
# 필터"하는 구조 자체가 안 맞음을 사용자가 지적) list/count 두 함수가
# 완전히 같은 조건을 만들어야 하므로 한 곳(_portfolio_filter_conditions)
# 에서 공유한다.
_SORT_COLUMNS = {
    "updated_at": "p.updated_at",
    "image_count": "image_count",
}


def _portfolio_filter_conditions(
    *,
    q: str | None,
    status_filter: str | None,
    needs_review: bool | None,
    review_reason_contains: str | None,
    construction_scope_filter: str | None,
    created_date: str | None,
) -> tuple[list[str], dict[str, Any]]:
    conditions = ["p.deleted_at IS NULL"]
    params: dict[str, Any] = {}
    if q:
        conditions.append(
            "(p.title ILIKE :q OR c.name ILIKE :q OR ac.name ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    if status_filter:
        conditions.append("p.status = :status_filter")
        params["status_filter"] = status_filter
    if needs_review is not None:
        conditions.append(
            "p.review_reason IS NOT NULL" if needs_review else "p.review_reason IS NULL"
        )
    if review_reason_contains:
        conditions.append("p.review_reason ILIKE :review_reason_contains")
        params["review_reason_contains"] = f"%{review_reason_contains}%"
    if construction_scope_filter:
        conditions.append("p.construction_scope = :construction_scope_filter")
        params["construction_scope_filter"] = construction_scope_filter
    if created_date:
        conditions.append("DATE(p.created_at) = :created_date")
        params["created_date"] = created_date
    return conditions, params


def list_portfolios(
    session: Session,
    *,
    q: str | None,
    status_filter: str | None,
    needs_review: bool | None,
    review_reason_contains: str | None = None,
    construction_scope_filter: str | None = None,
    created_date: str | None = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    conditions, params = _portfolio_filter_conditions(
        q=q,
        status_filter=status_filter,
        needs_review=needs_review,
        review_reason_contains=review_reason_contains,
        construction_scope_filter=construction_scope_filter,
        created_date=created_date,
    )
    params["limit"] = limit
    params["offset"] = offset
    where_clause = " AND ".join(conditions)
    sort_column = _SORT_COLUMNS.get(sort_by, _SORT_COLUMNS["updated_at"])
    sort_dir_sql = "ASC" if sort_dir == "asc" else "DESC"

    rows = session.execute(
        text(
            f"""
            SELECT
                p.id,
                p.company_id,
                c.name AS company_name,

                p.title,
                p.construction_scope,
                p.status,
                p.review_reason,

                p.complex_id,
                ac.name AS complex_name,

                p.representative_image_id,
                pi.thumbnail_path
                    AS representative_thumbnail_path,

                p.created_at,
                p.updated_at,
                sil.source_key IS NOT NULL AS has_source_url,
                (
                    SELECT COUNT(*)
                    FROM portfolio_images AS pi_count
                    WHERE pi_count.portfolio_id = p.id
                ) AS image_count
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN portfolio_images AS pi
              ON pi.id = p.representative_image_id
            LEFT JOIN source_import_links AS sil
              ON sil.entity_type = 'portfolio'
             AND sil.target_id = p.id
            WHERE {where_clause}
            ORDER BY {sort_column} {sort_dir_sql}, p.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


def count_portfolios(
    session: Session,
    *,
    q: str | None,
    status_filter: str | None,
    needs_review: bool | None,
    review_reason_contains: str | None = None,
    construction_scope_filter: str | None = None,
    created_date: str | None = None,
) -> int:
    conditions, params = _portfolio_filter_conditions(
        q=q,
        status_filter=status_filter,
        needs_review=needs_review,
        review_reason_contains=review_reason_contains,
        construction_scope_filter=construction_scope_filter,
        created_date=created_date,
    )
    where_clause = " AND ".join(conditions)

    row = session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            WHERE {where_clause}
            """
        ),
        params,
    ).mappings().one()

    return int(row["total"])


def find_portfolio_detail(
    session: Session,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                c.name AS company_name,

                p.title,
                p.summary,
                p.description,
                p.status,
                p.review_reason,

                p.complex_id,
                ac.name AS complex_name,

                p.updated_at,

                sil.source_key AS source_portfolio_id,
                sil.metadata ->> 'source_url' AS source_url
            FROM portfolios AS p
            JOIN companies AS c
              ON c.id = p.company_id
            LEFT JOIN apartment_complexes AS ac
              ON ac.id = p.complex_id
            LEFT JOIN source_import_links AS sil
              ON sil.entity_type = 'portfolio'
             AND sil.target_id = p.id
            WHERE p.id = :portfolio_id
              AND p.deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    if row is None:
        return None

    portfolio = dict(row)

    spaces = session.execute(
        text(
            """
            SELECT id, space_code, space_name, space_number, description, sort_order
            FROM portfolio_spaces
            WHERE portfolio_id = :portfolio_id
            ORDER BY sort_order, id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    images = session.execute(
        text(
            """
            SELECT id, portfolio_space_id, thumbnail_path, medium_path,
                   description, sort_order, is_representative
            FROM portfolio_images
            WHERE portfolio_id = :portfolio_id
            ORDER BY sort_order, id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().all()

    images_by_space: dict[int, list[dict[str, Any]]] = {}
    for image in images:
        images_by_space.setdefault(image["portfolio_space_id"], []).append(
            dict(image)
        )

    portfolio["spaces"] = [
        {**dict(space), "images": images_by_space.get(space["id"], [])}
        for space in spaces
    ]
    return portfolio


def update_portfolio_text(
    session: Session,
    *,
    portfolio_id: int,
    title: str | None,
    summary: str | None,
    description: str | None,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET title = COALESCE(:title, title),
                summary = :summary,
                description = :description,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND deleted_at IS NULL
            RETURNING id AS portfolio_id, title, summary, description
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "title": title,
            "summary": summary,
            "description": description,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def update_space_text(
    session: Session,
    *,
    portfolio_id: int,
    space_id: int,
    description: str | None,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolio_spaces
            SET description = :description,
                updated_at = NOW()
            WHERE id = :space_id
              AND portfolio_id = :portfolio_id
            RETURNING id, portfolio_id, description
            """
        ),
        {
            "space_id": space_id,
            "portfolio_id": portfolio_id,
            "description": description,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def assign_portfolio_complex(
    session: Session,
    *,
    portfolio_id: int,
    complex_id: int,
    apartment_type_id: int | None,
) -> dict[str, Any] | None:
    """v2.5.0: 관리자가 대량등록에서 단지/타입을 못 찾아 'draft'+review_reason
    으로 남은 포트폴리오에 단지(+선택적으로 타입)를 직접 지정한다.

    이 호출로 complex_id는 항상 채워지므로 'address_missing'/
    'complex_match_failed' 사유는 이 시점에 항상 해소된다. 타입까지 같이
    골랐으면(apartment_type_id 전달) 바로 'approved'로 전환하고, 단지만
    먼저 고치고 타입은 아직이면(apartment_type_id=NULL) 'apartment_type_missing'
    사유만 남긴 채 계속 'draft'로 둔다 -- 관리자가 나중에 같은 엔드포인트를
    타입까지 채워 다시 호출하면 그때 승인된다(주소만/타입만/둘다 미입력
    세 경우 모두 이 하나의 엔드포인트로 처리됨). 업체가 고치는 경로는
    기존 제출->승인 2단계를 그대로 거침(portfolios/service.py 참고)."""
    # :apartment_type_id를 SQL의 CASE 조건에서 NULL 비교로 직접 여러 번
    # 쓰면 `::bigint`류 캐스트와 콜론 바인드 문법이 겹쳐 파서 오류가 난다
    # (실제로 겪은 버그 -- psycopg SyntaxError). Python에서 완결 여부를
    # 먼저 계산해 별도 불리언 파라미터로 넘기는 쪽이 더 명확하고 안전하다.
    is_complete = apartment_type_id is not None
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET complex_id = :complex_id,
                apartment_type_id = :apartment_type_id,
                review_reason = CASE WHEN :is_complete THEN NULL ELSE 'apartment_type_missing' END,
                status = CASE WHEN :is_complete THEN 'approved' ELSE status END,
                published_at = CASE WHEN :is_complete THEN NOW() ELSE published_at END,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND deleted_at IS NULL
            RETURNING id AS portfolio_id, complex_id, apartment_type_id, status, review_reason
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "complex_id": complex_id,
            "apartment_type_id": apartment_type_id,
            "is_complete": is_complete,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def reorder_spaces(
    session: Session,
    *,
    portfolio_id: int,
    space_ids: list[int],
) -> int:
    """space_ids가 넘어온 순서 그대로 sort_order 0..N-1을 부여한다.
    이 포트폴리오 소속이 아닌 id는 조용히 무시한다(WHERE portfolio_id 체크)."""
    updated = 0
    for index, space_id in enumerate(space_ids):
        result = session.execute(
            text(
                """
                UPDATE portfolio_spaces
                SET sort_order = :sort_order,
                    updated_at = NOW()
                WHERE id = :space_id
                  AND portfolio_id = :portfolio_id
                """
            ),
            {
                "sort_order": index,
                "space_id": space_id,
                "portfolio_id": portfolio_id,
            },
        )
        updated += result.rowcount
    return updated


def find_portfolio(
    session: Session,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                p.id,
                p.company_id,
                p.title,
                p.status,
                p.rejection_reason,
                p.representative_image_id,
                p.published_at,
                p.deleted_at
            FROM portfolios AS p
            WHERE p.id = :portfolio_id
              AND p.deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def approve_portfolio(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'approved',
                rejection_reason = NULL,
                published_at = NOW(),
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND status = 'pending'
              AND deleted_at IS NULL
            RETURNING
                id AS portfolio_id,
                company_id,
                status,
                rejection_reason,
                published_at
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def reject_portfolio(
    session: Session,
    *,
    portfolio_id: int,
    reason: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'rejected',
                rejection_reason = :reason,
                published_at = NULL,
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND status = 'pending'
              AND deleted_at IS NULL
            RETURNING
                id AS portfolio_id,
                company_id,
                status,
                rejection_reason,
                published_at
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "reason": reason,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def hide_portfolio(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'hidden',
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND status = 'approved'
              AND deleted_at IS NULL
            RETURNING
                id AS portfolio_id,
                company_id,
                status,
                rejection_reason,
                published_at
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def unhide_portfolio(
    session: Session,
    *,
    portfolio_id: int,
) -> dict[str, Any] | None:
    """v2.5.0: 'hidden'을 다시 'approved'로 되돌린다. 이미 한 번 승인됐던
    포트폴리오를 다시 보여주는 것뿐이라 published_at은 hide_portfolio가
    건드리지 않은 그대로 재사용하고(다시 계산할 필요 없음), 관리자 재검수도
    거치지 않는다."""
    row = session.execute(
        text(
            """
            UPDATE portfolios
            SET status = 'approved',
                updated_at = NOW()
            WHERE id = :portfolio_id
              AND status = 'hidden'
              AND deleted_at IS NULL
            RETURNING
                id AS portfolio_id,
                company_id,
                status,
                rejection_reason,
                published_at
            """
        ),
        {"portfolio_id": portfolio_id},
    ).mappings().one_or_none()

    return dict(row) if row else None
