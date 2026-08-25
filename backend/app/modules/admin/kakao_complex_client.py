"""v2.5.1: 건물명만 있고 도로명주소가 없는 포트폴리오를 위해, 서버가
직접 카카오 로컬 API로 단지를 검색한다(REST API 키, 프론트의
kakao_js_key와는 별개). 프론트 `kakaoResolveBulkAddress()`(admin-api.js)
와 목표는 같다 -- 다만 그건 브라우저에서 관리자가 화면을 열어야만
동작하고, 이건 서버가 사람 개입 없이 처리한다(CLAUDE.md 4번 원칙).

두 단계로 조회한다:
1. 키워드(장소명) 검색으로 건물명 -> 도로명주소 후보를 찾는다. 카테고리가
   "아파트"로 명확히 분류된 결과만 신뢰한다(정문/관리사무소 같은 부속
   시설이 잘못 걸리는 것을 막기 위해) -- 애매하면 매칭 실패로 둔다,
   틀린 단지에 잘못 연결하는 것보다 확인필요로 남기는 게 안전하다.
2. 그 도로명주소를 다시 주소 검색 API에 넣어 sido/sigungu/eupmyeondong
   같은 행정구역 세분화 필드까지 채운다(키워드 검색 결과에는 이 필드가
   없음) -- 프론트가 반환하는 것과 동일한 형태로 맞추기 위함."""

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

KAKAO_API_BASE = "https://dapi.kakao.com/v2/local/search"
_TIMEOUT_SECONDS = 8

# v2.5.1: "창원 아파트"처럼 지역명+주거유형 일반명사뿐이고 실제 단지
# 고유명이 없는 검색어는, 카카오가 그 지역의 아무 아파트나 하나 반환해도
# 겉보기엔 "성공"처럼 보인다 -- 오매칭 위험이 커서 애초에 검색하지 않는다
# (오매칭보다 미매칭이 안전하다는 원칙). 반대로 "창원로얄아파트"처럼 지역명
# 뒤에 실제 이름이 덧붙은 경우는 아래 목록과 정확히(exact) 안 맞아서
# 정상적으로 검색을 진행한다 -- "~시/~구/~군/~읍/~면/~동/~리"로 끝나는
# 토큰은 접미사 규칙으로, 접미사 없는 축약형 시/군 이름(예: "창원",
# "군포")은 이 목록으로 따로 걸러야 한다.
_GENERIC_TYPE_WORDS = {
    "아파트", "오피스텔", "빌라", "연립주택", "연립", "다세대",
    "타운하우스", "주택", "빌리지", "맨션", "단지",
}
_BARE_REGION_NAMES = {
    "수원", "성남", "의정부", "안양", "부천", "광명", "평택", "동두천",
    "안산", "고양", "과천", "구리", "남양주", "오산", "시흥", "군포",
    "의왕", "하남", "용인", "파주", "이천", "안성", "김포", "화성",
    "광주", "양주", "포천", "여주", "연천", "가평", "양평",
    "춘천", "원주", "강릉", "동해", "태백", "속초", "삼척", "홍천",
    "횡성", "영월", "평창", "정선", "철원", "화천", "양구", "인제",
    "고성", "양양",
    "청주", "충주", "제천", "보은", "옥천", "영동", "증평", "진천",
    "괴산", "음성", "단양",
    "천안", "공주", "보령", "아산", "서산", "논산", "계룡", "당진",
    "금산", "부여", "서천", "청양", "홍성", "예산", "태안",
    "전주", "군산", "익산", "정읍", "남원", "김제", "완주", "진안",
    "무주", "장수", "임실", "순창", "고창", "부안",
    "목포", "여수", "순천", "나주", "광양", "담양", "곡성", "구례",
    "고흥", "보성", "화순", "장흥", "강진", "해남", "영암", "무안",
    "함평", "영광", "장성", "완도", "진도", "신안",
    "포항", "경주", "김천", "안동", "구미", "영주", "영천", "상주",
    "문경", "경산", "군위", "의성", "청송", "영양", "영덕", "청도",
    "고령", "성주", "칠곡", "예천", "봉화", "울진", "울릉",
    "창원", "진주", "통영", "사천", "김해", "밀양", "거제", "양산",
    "의령", "함안", "창녕", "남해", "하동", "산청", "함양", "거창",
    "합천",
    "제주", "서귀포",
    "서울", "부산", "대구", "인천", "대전", "울산", "세종",
}
_ADMIN_SUFFIX_RE = re.compile(r"^[가-힣]+(시|도|군|구|읍|면|동|리)$")


def _is_too_generic_query(query: str) -> bool:
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    remaining = {
        t for t in tokens
        if t not in _GENERIC_TYPE_WORDS
        and t not in _BARE_REGION_NAMES
        and not _ADMIN_SUFFIX_RE.match(t)
    }
    return not remaining


class KakaoComplexLookupError(ValueError):
    pass


def _request(path: str, params: dict[str, str]) -> dict[str, Any]:
    if not settings.kakao_rest_key:
        raise KakaoComplexLookupError("KAKAO_REST_KEY가 설정되어 있지 않습니다.")
    url = f"{KAKAO_API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"KakaoAK {settings.kakao_rest_key}",
            # 2026-08-22: 다른 외부 API 호출들과 동일하게 User-Agent를
            # 명시(정식 REST API 키로 인증하는 호출이라 차단 이력은
            # 없었지만, 빈 값보다는 명시하는 쪽이 안전).
            "User-Agent": "Zipterior/1.0 (+https://zipterior.kr)",
        },
    )
    # v2.5.1 일괄등록 속도저하(job #29) 원인 확인용 실측 로깅 -- 2026-08-21
    # (V2.5.0_PLAN.md 참고). 이 호출 자체가 병목인지 확정하기 위한 임시 계측이며,
    # JsonFormatter 필드 화이트리스트에 없는 값이라 메시지 문자열에 직접 넣는다.
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "카카오 API 호출 완료: path=%s query=%s duration_ms=%s",
            path, params.get("query"), elapsed_ms,
        )
        return body
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.warning(
            "카카오 API 호출 실패(HTTP %s): path=%s query=%s duration_ms=%s",
            exc.code, path, params.get("query"), elapsed_ms,
        )
        raise KakaoComplexLookupError(
            f"카카오 API 호출 실패({exc.code}): {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.warning(
            "카카오 API 연결 실패: path=%s query=%s duration_ms=%s reason=%s",
            path, params.get("query"), elapsed_ms, exc.reason,
        )
        raise KakaoComplexLookupError(f"카카오 API 연결 실패: {exc.reason}") from exc


def _keyword_search_road_address(building_name: str) -> tuple[str, str] | None:
    """(도로명주소, 카카오가 실제로 찾은 정식 장소명) 튜플을 돌려준다 --
    place_name까지 같이 돌려주는 이유: 검색에 쓴 문자열(예: "치평동
    금호대우")을 그대로 단지 이름으로 저장하면 지저분하다. 카카오가 찾은
    공식 명칭이 있으면 그걸 최종 단지 이름으로 쓰는 게 더 정확하다."""
    data = _request("keyword.json", {"query": building_name, "size": "5"})
    for document in data.get("documents") or []:
        category = str(document.get("category_name") or "")
        if "아파트" not in category:
            continue
        road_address = str(document.get("road_address_name") or "").strip()
        place_name = str(document.get("place_name") or "").strip()
        if road_address:
            return road_address, place_name
    return None


def search_complex_by_building_name(building_name: str) -> dict[str, Any] | None:
    """건물명으로 단지를 찾아 `_ensure_portfolio_complex`가 기대하는
    형태(name/road_address/jibun_address/sido/sigungu/eupmyeondong/
    latitude/longitude)로 돌려준다. 못 찾으면 None(예외 아님 -- 호출하는
    쪽이 기존 review_reason 흐름 그대로 확인필요로 남기면 된다)."""
    name = str(building_name or "").strip()
    if not name or _is_too_generic_query(name):
        return None

    keyword_result = _keyword_search_road_address(name)
    if not keyword_result:
        return None
    road_address, matched_place_name = keyword_result

    address_data = _request("address.json", {"query": road_address})
    documents = address_data.get("documents") or []
    if not documents:
        return None
    document = documents[0]
    road = document.get("road_address") or {}
    address = document.get("address") or {}

    return {
        # 카카오가 찾은 정식 명칭이 있으면 그걸 우선 쓴다 -- 검색에 쓴
        # 원본 문자열("치평동 금호대우" 등)보다 정확하고 깔끔하다.
        "name": matched_place_name or name,
        "road_address": str(
            road.get("address_name") or document.get("address_name") or road_address
        ),
        "jibun_address": str(address.get("address_name") or "") or None,
        "sido": str(address.get("region_1depth_name") or "") or None,
        "sigungu": str(address.get("region_2depth_name") or "") or None,
        "eupmyeondong": str(address.get("region_3depth_name") or "") or None,
        "latitude": float(document.get("y")),
        "longitude": float(document.get("x")),
    }
