#!/usr/bin/env python3
from __future__ import annotations

from app.core.config import settings


def main() -> int:
    warnings = settings.runtime_warnings()
    print(f"APP_ENV={settings.app_env}")
    print(f"APP_DEBUG={settings.app_debug}")
    print(f"RATE_LIMIT_ENABLED={settings.rate_limit_enabled}")
    print(f"JWT_SECRET_LENGTH={len(settings.jwt_secret_key)}")
    for warning in warnings:
        print(f"WARNING={warning}")
    if settings.is_production and settings.app_debug:
        print("PRODUCTION_READINESS_FAILED")
        return 1
    print("PRODUCTION_GUARD_OK")
    if settings.app_env.strip().lower() != "production":
        print("PRODUCTION_CUTOVER_PENDING")
    else:
        print("PRODUCTION_ENV_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
