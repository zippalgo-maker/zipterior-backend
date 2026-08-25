"""2026-08-25: 지도 통합검색창에 카카오 로컬 검색을 접목한다(사용자
요청). 원칙: 집테리어 DB(단지/업체)에 있는 결과를 항상 먼저 보여주고,
DB에 없는 것만 카카오로 보강한다 -- 그리고 보강 대상은 "아파트,
오피스텔, 지하철역"으로만 좁힌다(그 외 카테고리는 지도 서비스의
성격과 안 맞아서 노출하지 않음). 인테리어 업체는 이미 집테리어 DB로만
검색하므로 여기서 카카오를 보강할 필요가 없다.

`app/modules/admin/kakao_complex_client.py`와 같은 REST API 키
(settings.kakao_rest_key)를 재사용하지만, 그 모듈은 "건물명 하나에
대해 신뢰도 높은 단 하나의 매칭"을 찾는 게 목적(관리자 자동 매칭용)이라
검색어가 너무 일반적이면 아예 검색을 안 하는 등 보수적으로 짜여
있다. 이 모듈은 "검색창에 입력하는 대로 여러 후보를 보여주는" 목적이라
더 단순하게, 카테고리 텍스트로만 필터링한다."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_TIMEOUT_SECONDS = 3  # 검색창 타이핑 중 호출되므로 짧게 -- 느리면 그냥 DB 결과만 보여준다.

# category_name 문자열에 이 키워드가 들어있으면 보강 대상으로 인정하고,
# 화면에 보여줄 한글 라벨도 같이 결정한다(순서대로 검사 -- "지하철"이
# "아파트"보다 먼저 와야 "OO아파트역" 같은 역명 오분류를 피함).
_CATEGORY_LABELS: list[tuple[str, str]] = [
    ("지하철", "지하철역"),
    ("오피스텔", "오피스텔"),
    ("아파트", "아파트"),
]


def _place_category_label(category_name: str) -> str | None:
    for keyword, label in _CATEGORY_LABELS:
        if keyword in category_name:
            return label
    return None


def search_places(query: str, *, size: int = 8) -> list[dict[str, Any]]:
    """검색어로 카카오 키워드 검색을 호출해 아파트/오피스텔/지하철역만
    걸러 돌려준다. 키가 없거나 API 호출이 실패하면 조용히 빈 리스트를
    돌려준다(카카오 보강은 "있으면 좋은 것"이지, 이것 때문에 기존
    DB 검색까지 같이 실패하면 안 된다)."""
    if not settings.kakao_rest_key:
        return []
    if not query or len(query.strip()) < 2:
        return []

    url = f"{KAKAO_KEYWORD_SEARCH_URL}?{urllib.parse.urlencode({'query': query, 'size': str(size)})}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"KakaoAK {settings.kakao_rest_key}",
            "User-Agent": "Zipterior/1.0 (+https://zipterior.kr)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.warning("카카오 통합검색 보강 실패(HTTP %s): query=%s", exc.code, query)
        return []
    except urllib.error.URLError as exc:
        logger.warning("카카오 통합검색 보강 연결 실패: query=%s reason=%s", query, exc.reason)
        return []
    except Exception:
        logger.exception("카카오 통합검색 보강 중 예상 못한 오류: query=%s", query)
        return []

    results: list[dict[str, Any]] = []
    for document in data.get("documents") or []:
        category_name = str(document.get("category_name") or "")
        label = _place_category_label(category_name)
        if label is None:
            continue
        try:
            latitude = float(document.get("y"))
            longitude = float(document.get("x"))
        except (TypeError, ValueError):
            continue
        name = str(document.get("place_name") or "").strip()
        if not name:
            continue
        address = str(document.get("road_address_name") or document.get("address_name") or "").strip()
        results.append({
            "name": name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "place_category": label,
        })
    return results
