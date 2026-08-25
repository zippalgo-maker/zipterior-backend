from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_user_by_email(
    session: Session,
    email: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, email, role, status
            FROM users
            WHERE email = :email
              AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"email": email},
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_company_by_business_number(
    session: Session,
    business_number: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT id, name, business_number, status
            FROM companies
            WHERE business_number = :business_number
            LIMIT 1
            """
        ),
        {"business_number": business_number},
    ).mappings().one_or_none()

    return dict(row) if row else None


def create_company_user(
    session: Session,
    *,
    email: str,
    password_hash: str,
    name: str,
    phone: str | None,
    marketing_agreed: bool,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO users (
                    email,
                    password_hash,
                    name,
                    phone,
                    role,
                    status,
                    marketing_agreed
                )
                VALUES (
                    :email,
                    :password_hash,
                    :name,
                    :phone,
                    'company',
                    'active',
                    :marketing_agreed
                )
                RETURNING id
                """
            ),
            {
                "email": email,
                "password_hash": password_hash,
                "name": name,
                "phone": phone,
                "marketing_agreed": marketing_agreed,
            },
        ).scalar_one()
    )


def create_company(
    session: Session,
    *,
    owner_user_id: int,
    name: str,
    slug: str,
    business_number: str | None,
    representative_name: str,
    phone: str | None,
    email: str,
    postal_code: str | None,
    address: str | None,
    address_detail: str | None,
    sido: str | None,
    sigungu: str | None,
    eupmyeondong: str | None,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO companies (
                    owner_user_id,
                    name,
                    slug,
                    business_number,
                    representative_name,
                    phone,
                    email,
                    postal_code,
                    address,
                    address_detail,
                    sido,
                    sigungu,
                    eupmyeondong,
                    status,
                    consultation_available,
                    is_visible_on_map
                )
                VALUES (
                    :owner_user_id,
                    :name,
                    :slug,
                    :business_number,
                    :representative_name,
                    :phone,
                    :email,
                    :postal_code,
                    :address,
                    :address_detail,
                    :sido,
                    :sigungu,
                    :eupmyeondong,
                    'active',
                    TRUE,
                    FALSE
                )
                RETURNING id
                """
            ),
            {
                "owner_user_id": owner_user_id,
                "name": name,
                "slug": slug,
                "business_number": business_number,
                "representative_name": representative_name,
                "phone": phone,
                "email": email,
                "postal_code": postal_code,
                "address": address,
                "address_detail": address_detail,
                "sido": sido,
                "sigungu": sigungu,
                "eupmyeondong": eupmyeondong,
            },
        ).scalar_one()
    )


def create_owner_member(
    session: Session,
    *,
    company_id: int,
    user_id: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO company_members (
                company_id,
                user_id,
                member_role,
                status
            )
            VALUES (
                :company_id,
                :user_id,
                'owner',
                'active'
            )
            """
        ),
        {
            "company_id": company_id,
            "user_id": user_id,
        },
    )


def create_onboarding(
    session: Session,
    *,
    company_id: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO company_onboarding (
                company_id,
                status
            )
            VALUES (
                :company_id,
                'registering'
            )
            """
        ),
        {"company_id": company_id},
    )


def get_membership_plan(
    session: Session,
    plan_key: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                plan_key,
                display_name,
                duration_days
            FROM membership_plans
            WHERE plan_key = :plan_key
              AND is_active = TRUE
            LIMIT 1
            """
        ),
        {"plan_key": plan_key},
    ).mappings().one_or_none()

    return dict(row) if row else None


def create_membership(
    session: Session,
    *,
    company_id: int,
    plan_id: int,
    duration_days: int | None,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO company_memberships (
                    company_id,
                    plan_id,
                    status,
                    payment_required,
                    started_at,
                    expires_at
                )
                VALUES (
                    :company_id,
                    :plan_id,
                    'active',
                    FALSE,
                    NOW(),
                    CASE
                        WHEN CAST(:duration_days AS INTEGER) IS NULL THEN NULL
                        ELSE NOW() + make_interval(
                            days => CAST(:duration_days AS INTEGER)
                        )
                    END
                )
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "plan_id": plan_id,
                "duration_days": duration_days,
            },
        ).scalar_one()
    )


COMPANY_UPDATE_FIELDS = {
    "name",
    "representative_name",
    "phone",
    "postal_code",
    "address",
    "address_detail",
    "sido",
    "sigungu",
    "eupmyeondong",
    "latitude",
    "longitude",
    "intro",
    "website_url",
    "kakao_url",
    "consultation_available",
    "is_visible_on_map",
}


def find_company_for_user(
    session: Session,
    user_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                c.id,
                c.owner_user_id,
                cm.member_role,
                cm.status AS member_status,

                c.name,
                c.slug,
                c.business_number,
                c.representative_name,
                c.phone,
                c.email,

                c.postal_code,
                c.address,
                c.address_detail,
                c.sido,
                c.sigungu,
                c.eupmyeondong,

                c.latitude,
                c.longitude,

                c.intro,
                c.logo_path,
                c.website_url,
                c.kakao_url,

                c.status,
                c.consultation_available,
                c.is_visible_on_map,

                membership.plan_key AS membership_plan,
                membership.display_name AS membership_display_name,
                membership.membership_status,
                membership.expires_at AS membership_expires_at,
                COALESCE(
                    membership.features,
                    '{}'::jsonb
                ) AS membership_features,

                c.approved_at,
                c.created_at,
                c.updated_at
            FROM company_members AS cm
            JOIN companies AS c
              ON c.id = cm.company_id
            LEFT JOIN LATERAL (
                SELECT
                    mp.plan_key,
                    mp.display_name,
                    mp.features,
                    cms.status AS membership_status,
                    cms.expires_at
                FROM company_memberships AS cms
                JOIN membership_plans AS mp
                  ON mp.id = cms.plan_id
                WHERE cms.company_id = c.id
                ORDER BY
                    CASE
                        WHEN cms.status = 'active' THEN 0
                        ELSE 1
                    END,
                    cms.started_at DESC,
                    cms.id DESC
                LIMIT 1
            ) AS membership
              ON TRUE
            WHERE cm.user_id = :user_id
              AND cm.status = 'active'
              AND c.deleted_at IS NULL
            ORDER BY
                CASE
                    WHEN cm.member_role = 'owner' THEN 0
                    WHEN cm.member_role = 'manager' THEN 1
                    ELSE 2
                END,
                c.id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()

    return dict(row) if row else None


def update_company(
    session: Session,
    *,
    company_id: int,
    changes: dict[str, Any],
) -> None:
    safe_changes = {
        key: value
        for key, value in changes.items()
        if key in COMPANY_UPDATE_FIELDS
    }

    if not safe_changes:
        return

    assignments = [
        f"{column_name} = :{column_name}"
        for column_name in safe_changes
    ]
    assignments.append("updated_at = NOW()")

    query = text(
        f"""
        UPDATE companies
        SET {", ".join(assignments)}
        WHERE id = :company_id
          AND deleted_at IS NULL
        """
    )

    session.execute(
        query,
        {
            **safe_changes,
            "company_id": company_id,
        },
    )


def list_service_regions(
    session: Session,
    company_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
            ORDER BY
                is_primary DESC,
                sido,
                sigungu NULLS FIRST,
                eupmyeondong NULLS FIRST,
                id
            """
        ),
        {"company_id": company_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def count_service_regions(
    session: Session,
    company_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM company_service_regions
                WHERE company_id = :company_id
                """
            ),
            {"company_id": company_id},
        ).scalar_one()
    )


def find_service_region_by_code(
    session: Session,
    *,
    company_id: int,
    region_code: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
              AND region_code = :region_code
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "region_code": region_code,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_service_region_by_id(
    session: Session,
    *,
    company_id: int,
    region_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
              AND id = :region_id
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "region_id": region_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def clear_primary_service_region(
    session: Session,
    company_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE company_service_regions
            SET is_primary = FALSE
            WHERE company_id = :company_id
              AND is_primary = TRUE
            """
        ),
        {"company_id": company_id},
    )


def create_service_region(
    session: Session,
    *,
    company_id: int,
    region_code: str,
    sido: str,
    sigungu: str | None,
    eupmyeondong: str | None,
    is_primary: bool,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO company_service_regions (
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary
            )
            VALUES (
                :company_id,
                :region_code,
                :sido,
                :sigungu,
                :eupmyeondong,
                :is_primary
            )
            RETURNING
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            """
        ),
        {
            "company_id": company_id,
            "region_code": region_code,
            "sido": sido,
            "sigungu": sigungu,
            "eupmyeondong": eupmyeondong,
            "is_primary": is_primary,
        },
    ).mappings().one()

    return dict(row)


def delete_service_region(
    session: Session,
    *,
    company_id: int,
    region_id: int,
) -> bool:
    deleted_id = session.execute(
        text(
            """
            DELETE FROM company_service_regions
            WHERE company_id = :company_id
              AND id = :region_id
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "region_id": region_id,
        },
    ).scalar_one_or_none()

    return deleted_id is not None


def promote_oldest_service_region(
    session: Session,
    company_id: int,
) -> int | None:
    return session.execute(
        text(
            """
            WITH selected AS (
                SELECT id
                FROM company_service_regions
                WHERE company_id = :company_id
                ORDER BY created_at, id
                LIMIT 1
            )
            UPDATE company_service_regions AS csr
            SET is_primary = TRUE
            FROM selected
            WHERE csr.id = selected.id
            RETURNING csr.id
            """
        ),
        {"company_id": company_id},
    ).scalar_one_or_none()


def list_service_regions(
    session: Session,
    company_id: int,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
            ORDER BY
                is_primary DESC,
                sido,
                sigungu NULLS FIRST,
                eupmyeondong NULLS FIRST,
                id
            """
        ),
        {"company_id": company_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def count_service_regions(
    session: Session,
    company_id: int,
) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM company_service_regions
                WHERE company_id = :company_id
                """
            ),
            {"company_id": company_id},
        ).scalar_one()
    )


def find_service_region_by_code(
    session: Session,
    *,
    company_id: int,
    region_code: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
              AND region_code = :region_code
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "region_code": region_code,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def find_service_region_by_id(
    session: Session,
    *,
    company_id: int,
    region_id: int,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            FROM company_service_regions
            WHERE company_id = :company_id
              AND id = :region_id
            LIMIT 1
            """
        ),
        {
            "company_id": company_id,
            "region_id": region_id,
        },
    ).mappings().one_or_none()

    return dict(row) if row else None


def clear_primary_service_region(
    session: Session,
    company_id: int,
) -> None:
    session.execute(
        text(
            """
            UPDATE company_service_regions
            SET is_primary = FALSE
            WHERE company_id = :company_id
              AND is_primary = TRUE
            """
        ),
        {"company_id": company_id},
    )


def create_service_region(
    session: Session,
    *,
    company_id: int,
    region_code: str,
    sido: str,
    sigungu: str | None,
    eupmyeondong: str | None,
    is_primary: bool,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            INSERT INTO company_service_regions (
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary
            )
            VALUES (
                :company_id,
                :region_code,
                :sido,
                :sigungu,
                :eupmyeondong,
                :is_primary
            )
            RETURNING
                id,
                company_id,
                region_code,
                sido,
                sigungu,
                eupmyeondong,
                is_primary,
                created_at
            """
        ),
        {
            "company_id": company_id,
            "region_code": region_code,
            "sido": sido,
            "sigungu": sigungu,
            "eupmyeondong": eupmyeondong,
            "is_primary": is_primary,
        },
    ).mappings().one()

    return dict(row)


def delete_service_region(
    session: Session,
    *,
    company_id: int,
    region_id: int,
) -> bool:
    deleted_id = session.execute(
        text(
            """
            DELETE FROM company_service_regions
            WHERE company_id = :company_id
              AND id = :region_id
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "region_id": region_id,
        },
    ).scalar_one_or_none()

    return deleted_id is not None


def promote_oldest_service_region(
    session: Session,
    company_id: int,
) -> int | None:
    return session.execute(
        text(
            """
            WITH selected AS (
                SELECT id
                FROM company_service_regions
                WHERE company_id = :company_id
                ORDER BY created_at, id
                LIMIT 1
            )
            UPDATE company_service_regions AS csr
            SET is_primary = TRUE
            FROM selected
            WHERE csr.id = selected.id
            RETURNING csr.id
            """
        ),
        {"company_id": company_id},
    ).scalar_one_or_none()
