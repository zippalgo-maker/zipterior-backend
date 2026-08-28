from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


BASE_SELECT = """
SELECT
    er.id,
    er.customer_id,
    er.portfolio_id,
    er.complex_id,
    ac.name AS complex_name,
    er.apartment_type_id,
    apt.type_name AS apartment_type_name,
    apt.pyeong_label,
    er.title,
    er.description,
    er.desired_budget_min,
    er.desired_budget_max,
    er.desired_start_date,
    er.contact_method,
    er.allow_recommendations,
    er.status,
    er.created_at,
    er.updated_at,
    (
        SELECT COUNT(*)
        FROM estimate_request_companies erc
        WHERE erc.estimate_request_id = er.id
    ) AS assignment_count
FROM estimate_requests er
LEFT JOIN apartment_complexes ac ON ac.id = er.complex_id
LEFT JOIN apartment_types apt ON apt.id = er.apartment_type_id
"""


def validate_references(
    session: Session,
    *,
    portfolio_id: int | None,
    complex_id: int | None,
    apartment_type_id: int | None,
) -> dict[str, bool]:
    result = {
        "portfolio": True,
        "complex": True,
        "apartment_type": True,
        "apartment_type_matches_complex": True,
    }

    if portfolio_id is not None:
        result["portfolio"] = bool(
            session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM portfolios
                        WHERE id=:id
                          AND deleted_at IS NULL
                          AND status='approved'
                    )
                    """
                ),
                {"id": portfolio_id},
            ).scalar_one()
        )

    if complex_id is not None:
        result["complex"] = bool(
            session.execute(
                text("SELECT EXISTS (SELECT 1 FROM apartment_complexes WHERE id=:id AND is_active=TRUE)"),
                {"id": complex_id},
            ).scalar_one()
        )

    if apartment_type_id is not None:
        row = session.execute(
            text("SELECT id, complex_id FROM apartment_types WHERE id=:id"),
            {"id": apartment_type_id},
        ).mappings().one_or_none()
        result["apartment_type"] = row is not None
        if row is not None and complex_id is not None:
            result["apartment_type_matches_complex"] = row["complex_id"] == complex_id

    return result


def create_estimate(session: Session, *, customer_id: int, data: dict[str, Any]) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO estimate_requests (
                    customer_id, portfolio_id, complex_id, apartment_type_id,
                    title, description, desired_budget_min, desired_budget_max,
                    desired_start_date, contact_method, allow_recommendations,
                    status
                ) VALUES (
                    :customer_id, :portfolio_id, :complex_id, :apartment_type_id,
                    :title, :description, :desired_budget_min, :desired_budget_max,
                    :desired_start_date, :contact_method, :allow_recommendations,
                    'submitted'
                )
                RETURNING id
                """
            ),
            {"customer_id": customer_id, **data},
        ).scalar_one()
    )


def find_estimate(session: Session, *, estimate_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(BASE_SELECT + " WHERE er.id=:estimate_id"),
        {"estimate_id": estimate_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def find_customer_estimate(session: Session, *, estimate_id: int, customer_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(BASE_SELECT + " WHERE er.id=:estimate_id AND er.customer_id=:customer_id"),
        {"estimate_id": estimate_id, "customer_id": customer_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def find_estimate_by_id(session: Session, *, estimate_id: int) -> dict[str, Any] | None:
    """v1.10.1(2026-08-26): 시공 진행상황/리뷰는 고객뿐 아니라 업체도
    자기 견적인지 확인해야 해서, customer_id로 안 좁히는 조회가 필요."""
    row = session.execute(
        text(BASE_SELECT + " WHERE er.id=:estimate_id"),
        {"estimate_id": estimate_id},
    ).mappings().one_or_none()
    return dict(row) if row else None




def list_customer_estimates(session: Session, *, customer_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(BASE_SELECT + " WHERE er.customer_id=:customer_id ORDER BY er.created_at DESC, er.id DESC LIMIT :limit OFFSET :offset"),
        {"customer_id": customer_id, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(row) for row in rows]


def count_customer_estimates(session: Session, *, customer_id: int) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM estimate_requests WHERE customer_id=:customer_id"), {"customer_id": customer_id}).scalar_one())


def list_assignments(session: Session, *, estimate_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                c.id AS company_id, c.name AS company_name, c.phone AS company_phone,
                c.logo_path AS company_logo_path,
                erc.assignment_order, erc.assignment_score, erc.status,
                erc.assigned_at, erc.viewed_at, erc.responded_at
            FROM estimate_request_companies erc
            JOIN companies c ON c.id=erc.company_id
            WHERE erc.estimate_request_id=:estimate_id
            ORDER BY COALESCE(erc.assignment_order, 999999), erc.assigned_at, c.id
            """
        ),
        {"estimate_id": estimate_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def update_estimate_status(session: Session, *, estimate_id: int, status: str) -> bool:
    result = session.execute(
        text("UPDATE estimate_requests SET status=:status, updated_at=NOW() WHERE id=:estimate_id"),
        {"estimate_id": estimate_id, "status": status},
    )
    return result.rowcount == 1


def find_company_for_user(session: Session, *, user_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT c.id, c.name, c.status, cm.member_role, cm.status AS member_status
            FROM company_members cm
            JOIN companies c ON c.id=cm.company_id
            WHERE cm.user_id=:user_id
              AND cm.status='active'
              AND c.deleted_at IS NULL
            ORDER BY CASE WHEN cm.member_role='owner' THEN 0 ELSE 1 END, c.id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def find_company_assignment(session: Session, *, estimate_id: int, company_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT erc.*, er.status AS estimate_status
            FROM estimate_request_companies erc
            JOIN estimate_requests er ON er.id=erc.estimate_request_id
            WHERE erc.estimate_request_id=:estimate_id AND erc.company_id=:company_id
            """
        ),
        {"estimate_id": estimate_id, "company_id": company_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def list_company_estimates(session: Session, *, company_id: int, assignment_status: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
    conditions = ["erc.company_id=:company_id"]
    params: dict[str, Any] = {"company_id": company_id, "limit": limit, "offset": offset}
    if assignment_status:
        conditions.append("erc.status=:assignment_status")
        params["assignment_status"] = assignment_status
    rows = session.execute(
        text(
            BASE_SELECT
            + " JOIN estimate_request_companies erc ON erc.estimate_request_id=er.id "
            + f" WHERE {' AND '.join(conditions)} "
            + " ORDER BY erc.assigned_at DESC, er.id DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def count_company_estimates(session: Session, *, company_id: int, assignment_status: str | None) -> int:
    sql = "SELECT COUNT(*) FROM estimate_request_companies WHERE company_id=:company_id"
    params: dict[str, Any] = {"company_id": company_id}
    if assignment_status:
        sql += " AND status=:assignment_status"
        params["assignment_status"] = assignment_status
    return int(session.execute(text(sql), params).scalar_one())


def get_company_estimate(session: Session, *, estimate_id: int, company_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            BASE_SELECT
            + " JOIN estimate_request_companies erc ON erc.estimate_request_id=er.id "
            + " WHERE er.id=:estimate_id AND erc.company_id=:company_id"
        ),
        {"estimate_id": estimate_id, "company_id": company_id},
    ).mappings().one_or_none()
    if not row:
        return None
    data = dict(row)
    assignment = find_company_assignment(session, estimate_id=estimate_id, company_id=company_id)
    data.update({
        "assignment_status": assignment["status"],
        "assignment_order": assignment["assignment_order"],
        "assignment_score": assignment["assignment_score"],
        "assigned_at": assignment["assigned_at"],
        "viewed_at": assignment["viewed_at"],
        "responded_at": assignment["responded_at"],
    })
    return data


def update_assignment_status(session: Session, *, estimate_id: int, company_id: int, status: str) -> bool:
    viewed_clause = "viewed_at=COALESCE(viewed_at, NOW())," if status in {"viewed", "responded", "declined", "contracted"} else ""
    responded_clause = "responded_at=COALESCE(responded_at, NOW())," if status in {"responded", "declined", "contracted"} else ""
    sql = f"""
        UPDATE estimate_request_companies
        SET {viewed_clause} {responded_clause} status=:status
        WHERE estimate_request_id=:estimate_id AND company_id=:company_id
    """
    result = session.execute(text(sql), {"estimate_id": estimate_id, "company_id": company_id, "status": status})
    return result.rowcount == 1


def expire_other_assignments(session: Session, *, estimate_id: int, contracted_company_id: int) -> None:
    session.execute(
        text(
            """
            UPDATE estimate_request_companies
            SET status='expired'
            WHERE estimate_request_id=:estimate_id
              AND company_id<>:company_id
              AND status IN ('unread','viewed','responded')
            """
        ),
        {"estimate_id": estimate_id, "company_id": contracted_company_id},
    )


def list_admin_estimates(session: Session, *, estimate_status: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
    conditions = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if estimate_status:
        conditions.append("er.status=:estimate_status")
        params["estimate_status"] = estimate_status
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = session.execute(text(BASE_SELECT + where + " ORDER BY er.created_at DESC, er.id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
    return [dict(row) for row in rows]


def count_admin_estimates(session: Session, *, estimate_status: str | None) -> int:
    if estimate_status:
        return int(session.execute(text("SELECT COUNT(*) FROM estimate_requests WHERE status=:status"), {"status": estimate_status}).scalar_one())
    return int(session.execute(text("SELECT COUNT(*) FROM estimate_requests")).scalar_one())


# v2.5.1: 포트폴리오 CTA("이 포트폴리오의 집 인테리어 견적 문의하기")로
# 들어온 견적문의를 그 포트폴리오를 등록한 회사에 자동 배정하기 위한
# 조회. V2.5.0_PLAN.md 참고.
def get_portfolio_company_id(session: Session, *, portfolio_id: int) -> int | None:
    row = session.execute(
        text(
            "SELECT company_id FROM portfolios WHERE id=:id AND deleted_at IS NULL"
        ),
        {"id": portfolio_id},
    ).one_or_none()
    return int(row[0]) if row else None


def validate_active_companies(session: Session, *, company_ids: list[int]) -> list[int]:
    stmt = text("SELECT id FROM companies WHERE id IN :ids AND status='active' AND deleted_at IS NULL").bindparams(bindparam("ids", expanding=True))
    return [int(row[0]) for row in session.execute(stmt, {"ids": company_ids}).all()]


def assign_companies(session: Session, *, estimate_id: int, company_ids: list[int]) -> None:
    for order, company_id in enumerate(company_ids, start=1):
        session.execute(
            text(
                """
                INSERT INTO estimate_request_companies (
                    estimate_request_id, company_id, assignment_order, status
                ) VALUES (:estimate_id, :company_id, :assignment_order, 'unread')
                ON CONFLICT (estimate_request_id, company_id)
                DO UPDATE SET
                    assignment_order=EXCLUDED.assignment_order,
                    status=CASE
                        WHEN estimate_request_companies.status IN ('declined','expired') THEN 'unread'
                        ELSE estimate_request_companies.status
                    END
                """
            ),
            {"estimate_id": estimate_id, "company_id": company_id, "assignment_order": order},
        )
def list_estimate_images(session: Session, *, estimate_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT id, estimate_request_id, file_path, thumbnail_path, created_at
            FROM estimate_request_images
            WHERE estimate_request_id=:estimate_id
            ORDER BY created_at, id
            """
        ),
        {"estimate_id": estimate_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def count_estimate_images(session: Session, *, estimate_id: int) -> int:
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM estimate_request_images WHERE estimate_request_id=:estimate_id"),
            {"estimate_id": estimate_id},
        ).scalar_one()
    )


def create_estimate_image(session: Session, *, estimate_id: int, file_path: str, thumbnail_path: str | None = None) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO estimate_request_images (estimate_request_id, file_path, thumbnail_path)
            VALUES (:estimate_id, :file_path, :thumbnail_path)
            RETURNING id, estimate_request_id, file_path, thumbnail_path, created_at
            """
        ),
        {"estimate_id": estimate_id, "file_path": file_path, "thumbnail_path": thumbnail_path},
    ).mappings().one()
    return dict(row)


def find_estimate_image(session: Session, *, estimate_id: int, image_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, estimate_request_id, file_path, thumbnail_path, created_at
            FROM estimate_request_images
            WHERE id=:image_id AND estimate_request_id=:estimate_id
            """
        ),
        {"image_id": image_id, "estimate_id": estimate_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def delete_estimate_image(session: Session, *, estimate_id: int, image_id: int) -> bool:
    result = session.execute(
        text("DELETE FROM estimate_request_images WHERE id=:image_id AND estimate_request_id=:estimate_id"),
        {"image_id": image_id, "estimate_id": estimate_id},
    )
    return result.rowcount == 1


def find_estimate_region(session: Session, *, estimate_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT ac.sido, ac.sigungu, ac.eupmyeondong
            FROM estimate_requests er
            LEFT JOIN apartment_complexes ac ON ac.id=er.complex_id
            WHERE er.id=:estimate_id
            """
        ),
        {"estimate_id": estimate_id},
    ).mappings().one_or_none()
    return dict(row) if row else {"sido": None, "sigungu": None, "eupmyeondong": None}


def list_auto_assignment_candidates(
    session: Session,
    *,
    estimate_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    region = find_estimate_region(session, estimate_id=estimate_id)
    params = {
        "estimate_id": estimate_id,
        "sido": region.get("sido"),
        "sigungu": region.get("sigungu"),
        "limit": limit,
    }
    rows = session.execute(
        text(
            """
            SELECT
                c.id AS company_id,
                c.name AS company_name,
                COALESCE(css.estimate_base_score, 0) AS estimate_base_score,
                COALESCE((
                    SELECT MAX(mp.map_priority)
                    FROM company_memberships cmem
                    JOIN membership_plans mp ON mp.id=cmem.plan_id
                    WHERE cmem.company_id=c.id
                      AND cmem.status='active'
                      AND (cmem.expires_at IS NULL OR cmem.expires_at > NOW())
                      AND mp.is_active=TRUE
                ), 0) AS membership_priority,
                CASE
                    WHEN :sigungu IS NOT NULL AND EXISTS (
                        SELECT 1 FROM company_service_regions csr
                        WHERE csr.company_id=c.id AND csr.sigungu=:sigungu
                    ) THEN 60
                    WHEN :sigungu IS NOT NULL AND c.sigungu=:sigungu THEN 45
                    WHEN :sido IS NOT NULL AND EXISTS (
                        SELECT 1 FROM company_service_regions csr
                        WHERE csr.company_id=c.id AND csr.sido=:sido
                    ) THEN 30
                    WHEN :sido IS NOT NULL AND c.sido=:sido THEN 20
                    ELSE 0
                END AS region_score
            FROM companies c
            LEFT JOIN company_score_snapshots css ON css.company_id=c.id
            WHERE c.status='active'
              AND c.deleted_at IS NULL
              AND c.consultation_available=TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM estimate_request_companies erc
                  WHERE erc.estimate_request_id=:estimate_id
                    AND erc.company_id=c.id
                    AND erc.status NOT IN ('declined','expired')
              )
              AND (
                    :sido IS NULL
                    OR c.sido=:sido
                    OR EXISTS (
                        SELECT 1 FROM company_service_regions csr
                        WHERE csr.company_id=c.id AND csr.sido=:sido
                    )
              )
            ORDER BY
                region_score DESC,
                COALESCE(css.estimate_base_score, 0) DESC,
                membership_priority DESC,
                c.id ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        score = float(item["region_score"] or 0) + float(item["estimate_base_score"] or 0) + float(item["membership_priority"] or 0) * 5
        item["assignment_score"] = score
        item["score_breakdown"] = {
            "region_score": float(item["region_score"] or 0),
            "estimate_base_score": float(item["estimate_base_score"] or 0),
            "membership_priority": int(item["membership_priority"] or 0),
        }
        result.append(item)
    return result


def assign_scored_companies(session: Session, *, estimate_id: int, candidates: list[dict[str, Any]]) -> None:
    import json
    for order, candidate in enumerate(candidates, start=1):
        session.execute(
            text(
                """
                INSERT INTO estimate_request_companies (
                    estimate_request_id, company_id, assignment_order,
                    assignment_score, score_breakdown, status
                ) VALUES (
                    :estimate_id, :company_id, :assignment_order,
                    :assignment_score, CAST(:score_breakdown AS jsonb), 'unread'
                )
                ON CONFLICT (estimate_request_id, company_id)
                DO UPDATE SET
                    assignment_order=EXCLUDED.assignment_order,
                    assignment_score=EXCLUDED.assignment_score,
                    score_breakdown=EXCLUDED.score_breakdown,
                    assigned_at=NOW(),
                    status=CASE
                        WHEN estimate_request_companies.status IN ('declined','expired') THEN 'unread'
                        ELSE estimate_request_companies.status
                    END
                """
            ),
            {
                "estimate_id": estimate_id,
                "company_id": candidate["company_id"],
                "assignment_order": order,
                "assignment_score": candidate["assignment_score"],
                "score_breakdown": json.dumps(candidate["score_breakdown"], ensure_ascii=False),
            },
        )


def company_insights_window(session: Session, *, company_id: int, days_ago_start: int, days_ago_end: int) -> dict[str, Any]:
    """v2.5.41(2026-08-23) UX 도면 F9 -- `days_ago_start`~`days_ago_end` 일
    전 사이(예: 7~0=최근 1주, 14~7=그 전 1주)에 이 업체에 배정된 견적
    건수, 응답 건수, 놓친(declined/expired) 건수, 응답까지 걸린 평균
    시간을 한 번에 집계한다. 두 주를 한 함수로 반복 호출해 "지난주 대비"
    비교에 쓴다."""
    row = session.execute(
        text(
            """
            SELECT
                COUNT(*) AS assigned_count,
                COUNT(*) FILTER (WHERE status IN ('responded','contracted')) AS responded_count,
                COUNT(*) FILTER (WHERE status IN ('declined','expired')) AS declined_count,
                AVG(EXTRACT(EPOCH FROM (responded_at - assigned_at)) / 3600.0)
                    FILTER (WHERE responded_at IS NOT NULL) AS avg_response_hours
            FROM estimate_request_companies
            WHERE company_id=:company_id
              AND assigned_at >= NOW() - (:days_ago_start || ' days')::interval
              AND assigned_at < NOW() - (:days_ago_end || ' days')::interval
            """
        ),
        {"company_id": company_id, "days_ago_start": days_ago_start, "days_ago_end": days_ago_end},
    ).mappings().one()
    return dict(row)


def company_pending_over_24h(session: Session, *, company_id: int) -> int:
    """아직 응답 안 하고 24시간 넘게 대기 중인 배정 건수 -- "응답 지연"
    힌트에 쓴다."""
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*) FROM estimate_request_companies
                WHERE company_id=:company_id
                  AND status IN ('unread','viewed')
                  AND assigned_at < NOW() - INTERVAL '24 hours'
                """
            ),
            {"company_id": company_id},
        ).scalar_one()
    )


def company_avg_portfolio_images(session: Session, *, company_id: int) -> float | None:
    """공개(approved) 포트폴리오 기준 평균 등록 사진 수 -- "사진 부족"
    힌트에 쓴다. 포트폴리오가 하나도 없으면 None(사진 부족이 아니라
    포트폴리오 자체가 없는 경우라 다른 힌트로 안내해야 하므로 구분)."""
    row = session.execute(
        text(
            """
            SELECT AVG(img_count) AS avg_images FROM (
                SELECT p.id, COUNT(pi.id) AS img_count
                FROM portfolios p
                LEFT JOIN portfolio_images pi ON pi.portfolio_id=p.id
                WHERE p.company_id=:company_id AND p.status='approved'
                GROUP BY p.id
            ) t
            """
        ),
        {"company_id": company_id},
    ).scalar_one_or_none()
    return float(row) if row is not None else None


def list_company_notification_users(session: Session, *, company_ids: list[int]) -> list[dict[str, int]]:
    if not company_ids:
        return []
    stmt = text(
        """
        SELECT DISTINCT cm.company_id, cm.user_id
        FROM company_members cm
        JOIN users u ON u.id=cm.user_id
        WHERE cm.company_id IN :company_ids
          AND cm.status='active'
          AND cm.member_role IN ('owner','manager')
          AND u.status='active'
        """
    ).bindparams(bindparam("company_ids", expanding=True))
    rows = session.execute(stmt, {"company_ids": company_ids}).mappings().all()
    return [dict(row) for row in rows]


# v1.10.1(2026-08-26): 시공 진행상황(목업 13번 화면) -- 5단계 공정.
MILESTONE_PHASES = ["contract", "demolition", "mep", "carpentry_finish", "completion"]


def list_milestones(session: Session, *, estimate_id: int) -> list[dict[str, Any]]:
    # seed_milestones()가 MILESTONE_PHASES 순서 그대로 순차 INSERT하므로
    # id 오름차순 정렬이 곧 공정 순서와 같다(array_position 등 굳이
    # 파라미터 배열을 안 써도 됨).
    rows = session.execute(
        text(
            "SELECT phase_key, status, note, completed_at, updated_at "
            "FROM estimate_milestones WHERE estimate_request_id=:eid ORDER BY id"
        ),
        {"eid": estimate_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def seed_milestones(session: Session, *, estimate_id: int, all_done: bool) -> None:
    """계약(contracted) 시점엔 1단계(계약완료)만 done, 준공(closed)
    시점엔 5단계 전부 done으로 처음 조회될 때 한 번 채워 넣는다(회사가
    실제로 갱신하기 전까지의 합리적인 기본값)."""
    for phase in MILESTONE_PHASES:
        done = all_done or phase == "contract"
        session.execute(
            text(
                "INSERT INTO estimate_milestones(estimate_request_id, phase_key, status, completed_at) "
                "VALUES (:eid, :phase, :status, CASE WHEN :done THEN NOW() ELSE NULL END) "
                "ON CONFLICT (estimate_request_id, phase_key) DO NOTHING"
            ),
            {"eid": estimate_id, "phase": phase, "status": "done" if done else "pending", "done": done},
        )
    session.commit()


def upsert_milestone(session: Session, *, estimate_id: int, phase_key: str, status: str, note: str | None) -> None:
    # v1.10.1(2026-08-26): :status를 컬럼 대입("status=:status")과 비교
    # ("CASE WHEN :status=..") 양쪽에 같이 쓰면 psycopg가 서로 다른
    # 타입(character varying vs text)으로 추론해 AmbiguousParameter가
    # 남(이 코드베이스에서 이미 한 번 겪었던 패턴, public_map/repository.py
    # 참고). CAST(:status AS varchar)로 비교 쪽 타입을 고정해서 해결.
    session.execute(
        text(
            "INSERT INTO estimate_milestones(estimate_request_id, phase_key, status, note, completed_at, updated_at) "
            "VALUES (:eid, :phase, :status, :note, CASE WHEN CAST(:status AS varchar)='done' THEN NOW() ELSE NULL END, NOW()) "
            "ON CONFLICT (estimate_request_id, phase_key) DO UPDATE SET "
            "status=:status, note=:note, "
            "completed_at=CASE WHEN CAST(:status AS varchar)='done' THEN NOW() ELSE NULL END, updated_at=NOW()"
        ),
        {"eid": estimate_id, "phase": phase_key, "status": status, "note": note},
    )
    session.commit()
