import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_base_feature(
    session: Session,
    feature_key: str,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT
            feature_key,
            display_name,
            is_enabled,
            read_enabled,
            write_enabled,
            settings
        FROM system_features
        WHERE feature_key = :feature_key
        """
    )

    row = session.execute(
        query,
        {"feature_key": feature_key},
    ).mappings().one_or_none()

    return dict(row) if row else None


def get_matching_scopes(
    session: Session,
    feature_key: str,
    scopes: dict[str, str],
) -> list[dict[str, Any]]:
    if not scopes:
        return []

    now = datetime.now(timezone.utc)
    scope_conditions: list[str] = []

    params: dict[str, Any] = {
        "feature_key": feature_key,
        "now": now,
    }

    for index, (scope_type, scope_value) in enumerate(scopes.items()):
        type_param = f"scope_type_{index}"
        value_param = f"scope_value_{index}"

        scope_conditions.append(
            f"""
            (
                scope_type = :{type_param}
                AND scope_value = :{value_param}
            )
            """
        )

        params[type_param] = scope_type
        params[value_param] = scope_value

    query = text(
        f"""
        SELECT
            scope_type,
            scope_value,
            is_enabled,
            read_enabled,
            write_enabled,
            settings
        FROM system_feature_scopes
        WHERE feature_key = :feature_key
          AND ({" OR ".join(scope_conditions)})
          AND (
              starts_at IS NULL
              OR starts_at <= :now
          )
          AND (
              ends_at IS NULL
              OR ends_at > :now
          )
        """
    )

    return [
        dict(row)
        for row in session.execute(query, params).mappings()
    ]


# v2.5.1: 포트폴리오 하단 표시 설정(SNS링크 노출/하단 안내문구) 전용
# 조회·갱신. system_features의 is_enabled(토글)와 settings(jsonb) 필드를
# 그대로 재사용한다 -- 별도 테이블/마이그레이션 없이 기존 범용 설정
# 테이블에 새 feature_key 2개만 얹는 방식(V2.5.0_PLAN.md 참고).
def set_feature_enabled(
    session: Session,
    *,
    feature_key: str,
    is_enabled: bool,
    updated_by: int | None,
) -> None:
    session.execute(
        text(
            """
            UPDATE system_features
            SET is_enabled = :is_enabled,
                updated_by = :updated_by,
                updated_at = now()
            WHERE feature_key = :feature_key
            """
        ),
        {
            "feature_key": feature_key,
            "is_enabled": is_enabled,
            "updated_by": updated_by,
        },
    )


def merge_feature_settings(
    session: Session,
    *,
    feature_key: str,
    patch: dict[str, Any],
    updated_by: int | None,
) -> None:
    """settings jsonb에 patch만 덮어씌운다(명시 안 한 기존 키는 그대로
    유지) -- PATCH가 부분 갱신을 지원하도록."""
    session.execute(
        text(
            """
            UPDATE system_features
            SET settings = settings || CAST(:patch AS jsonb),
                updated_by = :updated_by,
                updated_at = now()
            WHERE feature_key = :feature_key
            """
        ),
        {
            "feature_key": feature_key,
            "patch": json.dumps(patch),
            "updated_by": updated_by,
        },
    )
