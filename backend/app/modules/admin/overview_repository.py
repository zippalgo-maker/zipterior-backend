from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session


def dashboard(session: Session) -> dict[str, int]:
    row = session.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM users
             WHERE deleted_at IS NULL
               AND role IN ('customer','company')) AS total_users,
          (SELECT COUNT(*) FROM companies WHERE deleted_at IS NULL) AS total_companies,
          (SELECT COUNT(*) FROM companies WHERE deleted_at IS NULL AND status IN ('pending','onboarding','prospect')) AS pending_companies,
          (SELECT COUNT(*) FROM portfolios WHERE deleted_at IS NULL AND status='submitted') AS pending_portfolios,
          (SELECT COUNT(*) FROM estimate_requests WHERE status NOT IN ('cancelled','completed','expired')) AS active_estimates,
          (SELECT COUNT(*) FROM reports WHERE target_type='portfolio_comment' AND status IN ('received','reviewing')) AS open_comment_reports
    """)).mappings().one()
    return {k: int(v or 0) for k, v in row.items()}


def list_users(
    session: Session,
    *,
    q: str | None,
    role: str | None,
    user_status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    where = ["u.deleted_at IS NULL"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if q:
        where.append(
            "(u.email::text ILIKE :q "
            "OR u.name ILIKE :q "
            "OR COALESCE(u.nickname,'') ILIKE :q "
            "OR COALESCE(u.phone,'') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if role:
        where.append("u.role=:role")
        params["role"] = role

    if user_status:
        where.append("u.status=:status")
        params["status"] = user_status

    clause = " AND ".join(where)

    total = int(
        session.execute(
            text(f"SELECT COUNT(*) FROM users u WHERE {clause}"),
            params,
        ).scalar_one()
    )

    rows = session.execute(
        text(f"""
            SELECT
                u.id,
                u.email::text AS email,
                u.name,
                u.nickname,
                u.phone,
                u.role,
                u.status,

                CASE
                    WHEN u.role='company'
                    THEN membership.plan_key
                    ELSE NULL
                END AS membership_plan,

                CASE
                    WHEN u.role='company'
                    THEN membership.display_name
                    ELSE NULL
                END AS membership_display_name,

                CASE
                    WHEN u.role='company'
                    THEN membership.membership_status
                    ELSE NULL
                END AS membership_status,

                u.last_login_at,
                u.created_at,
                oauth.providers AS oauth_providers

            FROM users u

            LEFT JOIN LATERAL (
                SELECT array_agg(o.provider ORDER BY o.provider) AS providers
                FROM user_oauth_accounts o
                WHERE o.user_id = u.id
            ) oauth ON TRUE

            LEFT JOIN LATERAL (
                SELECT cm.company_id
                FROM company_members cm
                WHERE cm.user_id=u.id
                  AND cm.status='active'
                ORDER BY
                    CASE cm.member_role
                        WHEN 'owner' THEN 0
                        WHEN 'manager' THEN 1
                        ELSE 2
                    END,
                    cm.created_at ASC
                LIMIT 1
            ) member_company ON TRUE

            LEFT JOIN LATERAL (
                SELECT
                    mp.plan_key,
                    mp.display_name,
                    cms.status AS membership_status
                FROM company_memberships cms
                JOIN membership_plans mp
                  ON mp.id=cms.plan_id
                WHERE cms.company_id=member_company.company_id
                ORDER BY
                    CASE WHEN cms.status='active' THEN 0 ELSE 1 END,
                    cms.started_at DESC NULLS LAST,
                    cms.id DESC
                LIMIT 1
            ) membership ON TRUE

            WHERE {clause}
            ORDER BY u.id DESC
            LIMIT :limit
            OFFSET :offset
        """),
        params,
    ).mappings().all()

    items = [dict(r) for r in rows]
    for item in items:
        item["oauth_providers"] = item["oauth_providers"] or []
    return items, total

# 2026-08-25(관리자 업체관리 필터/검색/일괄승인/상세 추가): q/status만
# 있던 필터에 지역(sido)·등급(plan_key, company_memberships의 활성
# 멤버십->membership_plans) 조건을 추가하고, 목록에도 plan_key/
# plan_display_name/portfolio_count를 같이 내려준다(화면에서 등급
# 배지·시공사례 수를 바로 보여주기 위함). 활성 멤버십이 없는 업체는
# free(일반) 취급(LEFT JOIN + COALESCE) -- 실제로 신규가입 직후엔
# company_memberships row가 없을 수 있어서 free를 기본값으로 삼는 게
# 맞다(무료 요금제라는 개념 자체가 "멤버십 미가입 상태"와 동치).
def list_companies(session: Session, *, q: str | None, company_status: str | None, sido: str | None = None, plan_key: str | None = None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    where = ["c.deleted_at IS NULL"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        where.append("(c.name ILIKE :q OR COALESCE(c.business_number,'') ILIKE :q OR COALESCE(c.phone,'') ILIKE :q OR COALESCE(c.email::text,'') ILIKE :q)")
        params["q"] = f"%{q}%"
    if company_status:
        where.append("c.status=:status"); params["status"] = company_status
    if sido:
        where.append("c.sido=:sido"); params["sido"] = sido
    if plan_key:
        where.append("COALESCE(mp.plan_key,'free')=:plan_key"); params["plan_key"] = plan_key
    clause = " AND ".join(where)
    membership_join = """
        LEFT JOIN LATERAL (
            SELECT plan_id FROM company_memberships cm
            WHERE cm.company_id=c.id AND cm.status='active'
              AND (cm.expires_at IS NULL OR cm.expires_at > NOW())
            ORDER BY cm.started_at DESC LIMIT 1
        ) active_cm ON TRUE
        LEFT JOIN membership_plans mp ON mp.id=active_cm.plan_id
    """
    total = int(session.execute(text(f"""
        SELECT COUNT(*) FROM companies c {membership_join} WHERE {clause}
    """), params).scalar_one())
    rows = session.execute(text(f"""
        SELECT c.id,c.owner_user_id,c.name,c.business_number,c.representative_name,c.phone,c.email::text AS email,
               c.sido,c.sigungu,c.status,c.consultation_available,c.is_visible_on_map,
               (c.latitude IS NOT NULL AND c.longitude IS NOT NULL) AS has_map_coordinates,
               c.approved_at,c.created_at,
               COALESCE(mp.plan_key,'free') AS plan_key,
               COALESCE(mp.display_name,'일반') AS plan_display_name,
               (SELECT COUNT(*) FROM portfolios p WHERE p.company_id=c.id AND p.status='approved' AND p.deleted_at IS NULL) AS portfolio_count,
               (SELECT COUNT(*) FROM company_sales_contacts sc WHERE sc.company_id=c.id) AS sales_contact_count,
               (SELECT MAX(sc.contacted_at) FROM company_sales_contacts sc WHERE sc.company_id=c.id) AS last_sales_contact_at
        FROM companies c {membership_join}
        WHERE {clause}
        ORDER BY c.id DESC LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    return [dict(r) for r in rows], total


# 2026-08-25: 업체관리 "상세보기" -- 회원 상세(get_user_detail)와 같은
# 패턴. 프로필 전체 + 소유자 계정 + 활성 멤버십 + 시공사례/찜 통계 +
# 최근 등록 포트폴리오 몇 건을 한 번에 내려줘서 모달 하나로 다 보이게.
def get_company_detail(session: Session, company_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                c.id, c.owner_user_id, c.name, c.slug, c.business_number,
                c.representative_name, c.phone, c.email::text AS email,
                c.postal_code, c.address, c.address_detail, c.sido, c.sigungu, c.eupmyeondong,
                c.latitude, c.longitude, c.intro, c.logo_path, c.website_url, c.kakao_url,
                c.status, c.consultation_available, c.is_visible_on_map,
                c.suspended_reason, c.suspended_until,
                c.approved_at, c.approved_by, c.created_at, c.updated_at,
                u.email::text AS owner_email, u.name AS owner_name, u.phone AS owner_phone,
                u.status AS owner_status, u.last_login_at AS owner_last_login_at,
                COALESCE(mp.plan_key,'free') AS plan_key,
                COALESCE(mp.display_name,'일반') AS plan_display_name,
                cm.started_at AS membership_started_at, cm.expires_at AS membership_expires_at,
                (SELECT COUNT(*) FROM portfolios p WHERE p.company_id=c.id AND p.deleted_at IS NULL) AS portfolio_total,
                (SELECT COUNT(*) FROM portfolios p WHERE p.company_id=c.id AND p.status='approved' AND p.deleted_at IS NULL) AS portfolio_approved,
                (SELECT COUNT(*) FROM portfolios p WHERE p.company_id=c.id AND p.status='pending' AND p.deleted_at IS NULL) AS portfolio_pending
            FROM companies c
            LEFT JOIN users u ON u.id=c.owner_user_id
            LEFT JOIN LATERAL (
                SELECT id, plan_id, started_at, expires_at FROM company_memberships cm2
                WHERE cm2.company_id=c.id AND cm2.status='active'
                  AND (cm2.expires_at IS NULL OR cm2.expires_at > NOW())
                ORDER BY cm2.started_at DESC LIMIT 1
            ) cm ON TRUE
            LEFT JOIN membership_plans mp ON mp.id=cm.plan_id
            WHERE c.id=:company_id AND c.deleted_at IS NULL
            """
        ),
        {"company_id": company_id},
    ).mappings().one_or_none()
    if row is None:
        return None
    result = dict(row)
    portfolios = session.execute(
        text(
            """
            SELECT id, title, status, created_at
            FROM portfolios
            WHERE company_id=:company_id AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT 5
            """
        ),
        {"company_id": company_id},
    ).mappings().all()
    result["recent_portfolios"] = [dict(r) for r in portfolios]
    return result


def list_action_logs(session: Session, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    total = int(session.execute(text("SELECT COUNT(*) FROM admin_action_logs")).scalar_one())
    rows = session.execute(text("""
        SELECT id,admin_user_id,action_type,target_type,target_id,reason,created_at
        FROM admin_action_logs ORDER BY id DESC LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()
    return [dict(r) for r in rows], total


# 2026-08-24: 회원 상세(로그인정보/SNS 연동) -- admin-dashboard.html의
# "상세" 버튼이 이미 마크업엔 있었지만 클릭하면 "다음 관리자
# 고도화에서 확장합니다" 토스트만 뜨던 스텁을 채운다.
def get_user_detail(session: Session, user_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                u.id,
                u.email::text AS email,
                u.name,
                u.nickname,
                u.phone,
                u.role,
                u.status,
                u.suspended_reason,
                u.suspended_until,
                (u.password_hash IS NOT NULL) AS has_password,
                (u.email::text LIKE '%@no-email.zipterior.kr') AS is_placeholder_email,
                u.email_verified_at,
                u.last_login_at,
                u.created_at
            FROM users u
            WHERE u.id = :user_id
              AND u.deleted_at IS NULL
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def list_oauth_accounts_for_user(session: Session, user_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT id, provider, provider_user_id, email, created_at
            FROM user_oauth_accounts
            WHERE user_id = :user_id
            ORDER BY created_at ASC
            """
        ),
        {"user_id": user_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def count_oauth_accounts_for_user(session: Session, user_id: int) -> int:
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM user_oauth_accounts WHERE user_id=:user_id"),
            {"user_id": user_id},
        ).scalar_one()
    )


def find_oauth_account_by_user_and_provider(
    session: Session,
    *,
    user_id: int,
    provider: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, user_id, provider, provider_user_id, email, created_at
            FROM user_oauth_accounts
            WHERE user_id = :user_id
              AND provider = :provider
            """
        ),
        {"user_id": user_id, "provider": provider},
    ).mappings().one_or_none()
    return dict(row) if row else None


def delete_oauth_account(session: Session, oauth_account_id: int) -> None:
    session.execute(
        text("DELETE FROM user_oauth_accounts WHERE id=:id"),
        {"id": oauth_account_id},
    )


def list_login_attempts(
    session: Session,
    *,
    user_id: int,
    email: str,
    limit: int,
) -> list[dict[str, Any]]:
    # user_id로만 걸면 놓친다 -- 로그인 실패 시도(예: 비밀번호 틀림)는
    # 계정을 아직 특정 못 해 user_id가 NULL로 기록되고 email만 남는다
    # (auth/repository.py record_login_attempt 참고). 이메일도 같이
    # 매칭해야 그 계정을 노린 실패 시도까지 전부 보인다.
    rows = session.execute(
        text(
            """
            SELECT id, was_successful, failure_reason,
                   host(ip_address) AS ip_address, user_agent,
                   device_name, created_at
            FROM auth_login_attempts
            WHERE user_id = :user_id OR email = :email
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "email": email, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def revoke_user_sessions(session: Session, user_id: int, reason: str) -> int:
    # admin/repository.py revoke_owner_refresh_tokens와 동일 패턴(그
    # 함수를 import해서 재사용하는 대신 그대로 복제) -- 이 모듈군은
    # auth 모듈 내부 구현에 직접 의존하지 않는 기존 관례를 따름.
    result = session.execute(
        text(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()),
                revoke_reason = COALESCE(revoke_reason, :reason)
            WHERE user_id = :user_id
              AND revoked_at IS NULL
            """
        ),
        {"user_id": user_id, "reason": reason},
    )
    return int(result.rowcount or 0)


def list_orphaned_oauth_accounts(session: Session) -> list[dict[str, Any]]:
    """user_id가 가리키는 계정이 이미 없거나(탈퇴 등) 삭제된 SNS
    연동 레코드 -- oauth/service.py handle_callback이 로그인 시점에
    이미 "연결된 계정을 찾을 수 없습니다"로 명시적으로 막아두는
    예외 상황과 동일 케이스를 관리자가 미리 찾아 정리할 수 있게."""
    rows = session.execute(
        text(
            """
            SELECT o.id, o.user_id, o.provider, o.provider_user_id,
                   o.email, o.created_at
            FROM user_oauth_accounts o
            LEFT JOIN users u
              ON u.id = o.user_id AND u.deleted_at IS NULL
            WHERE u.id IS NULL
            ORDER BY o.created_at DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]

