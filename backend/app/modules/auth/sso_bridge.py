"""집팔고360 SSO 1회용 코드를 서버 간 통신으로 검증한다.

집팔고360(apps/api/app/modules/auth/router.py)의 POST /api/auth/sso/verify를
호출한다. 이 서버엔 httpx/requests가 설치되어 있지 않고(naver_complex_client.py
등 기존 코드도 stdlib urllib만 씀) 같은 관례를 따라 urllib만 쓴다.
"""
import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings

REQUEST_TIMEOUT_SECONDS = 5


def verify_code_with_zippalgo360(code: str) -> dict[str, Any] | None:
    if not settings.sso_shared_secret:
        return None

    url = f"{settings.zippalgo360_api_base_url}/api/auth/sso/verify"
    body = json.dumps({"code": code}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.sso_shared_secret}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None

    if not isinstance(data, dict) or "email" not in data:
        return None

    return data
