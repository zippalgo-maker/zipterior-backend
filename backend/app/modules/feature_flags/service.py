from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.modules.feature_flags import repository


SCOPE_PRIORITY = {
    "environment": 10,
    "role": 20,
    "company_grade": 30,
    "region": 40,
    "channel": 50,
    "user": 100,
}


@dataclass
class FeatureDecision:
    feature_key: str
    display_name: str
    is_enabled: bool
    read_enabled: bool
    write_enabled: bool
    settings: dict[str, Any] = field(default_factory=dict)
    applied_scopes: list[dict[str, str]] = field(
        default_factory=list
    )


class FeatureFlagService:
    @staticmethod
    def evaluate(
        session: Session,
        feature_key: str,
        scopes: dict[str, str] | None = None,
    ) -> FeatureDecision:
        base = repository.get_base_feature(
            session,
            feature_key,
        )

        if base is None:
            return FeatureDecision(
                feature_key=feature_key,
                display_name=feature_key,
                is_enabled=False,
                read_enabled=False,
                write_enabled=False,
            )

        decision = FeatureDecision(
            feature_key=feature_key,
            display_name=base["display_name"],
            is_enabled=base["is_enabled"],
            read_enabled=base["read_enabled"],
            write_enabled=base["write_enabled"],
            settings=dict(base["settings"] or {}),
        )

        matches = repository.get_matching_scopes(
            session,
            feature_key,
            scopes or {},
        )

        matches.sort(
            key=lambda item: SCOPE_PRIORITY.get(
                item["scope_type"],
                0,
            )
        )

        for scope in matches:
            decision.is_enabled = scope["is_enabled"]
            decision.read_enabled = scope["read_enabled"]
            decision.write_enabled = scope["write_enabled"]
            decision.settings.update(scope["settings"] or {})
            decision.applied_scopes.append(
                {
                    "scope_type": scope["scope_type"],
                    "scope_value": scope["scope_value"],
                }
            )

        return decision

    @classmethod
    def require_read(
        cls,
        session: Session,
        feature_key: str,
        scopes: dict[str, str] | None = None,
    ) -> FeatureDecision:
        decision = cls.evaluate(
            session,
            feature_key,
            scopes,
        )

        if not decision.is_enabled or not decision.read_enabled:
            raise PermissionError(
                f"읽기가 비활성화된 기능입니다: {feature_key}"
            )

        return decision

    @classmethod
    def require_write(
        cls,
        session: Session,
        feature_key: str,
        scopes: dict[str, str] | None = None,
    ) -> FeatureDecision:
        decision = cls.evaluate(
            session,
            feature_key,
            scopes,
        )

        if not decision.is_enabled or not decision.write_enabled:
            raise PermissionError(
                f"쓰기가 비활성화된 기능입니다: {feature_key}"
            )

        return decision
