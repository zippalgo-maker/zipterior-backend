import gzip
import http.cookiejar
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Any


NAVER_MAP_URL = (
    "https://fin.land.naver.com/map?zoom=17&tradeTypes=A1&"
    "realEstateTypes=A01-A02&rentPrice=0-4950000&showRealtors=true"
)
NAVER_API_BASE = "https://fin.land.naver.com/front-api/v1"
NAVER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) "
    "Gecko/20100101 Firefox/149.0"
)

# v2.5.1: 시군구 기준 자동수집 1단계(법정동 안의 단지 목록)에 쓴다. 이
# 모바일 API는 fin.land.naver.com과 달리 세션 쿠키 없이 단순 GET만으로
# 응답하는 것을 실제 호출로 확인했다(V2.5.0_PLAN.md 참고). 여기서 나오는
# hscpNo가 NAVER_API_BASE의 complexNumber와 동일한 값임도 확인했다.
MLAND_API_BASE = "https://m.land.naver.com"
MLAND_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

HEATING_SYSTEM_LABELS = {
    "HT001": "개별난방",
    "HT002": "중앙난방",
    "HT003": "개별냉난방",
    "HT004": "중앙냉난방",
    "HT005": "지역난방",
    "HT006": "지역냉난방",
}
HEATING_ENERGY_LABELS = {
    "HF001": "도시가스",
    "HF002": "열병합",
    "HF003": "기름",
    "HF004": "전기",
    "HF005": "심야전기",
    "HF006": "태양열",
    "HF007": "LPG",
    "HF008": "지열",
}


class NaverComplexLookupError(ValueError):
    pass


def _normalize_complex_name(value: str | None) -> str:
    # 카카오와 네이버가 덧붙이는 아파트·주상복합 표기를 제거해 같은 단지만 비교한다.
    normalized = re.sub(r"\([^)]*\)", "", str(value or "")).lower()
    normalized = normalized.replace("아파트", "").replace("주상복합", "")
    return re.sub(r"[^0-9a-z가-힣]", "", normalized)


def _distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius = 6371.0
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _has_floor_plan_variant(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_floor_plan_variant(item) for item in value.values())
    if isinstance(value, list):
        return any(bool(item) for item in value)
    return bool(value)


class NaverComplexClient:
    """관리자 요청 1건마다 네이버 세션을 새로 만들고 텍스트정보만 반환한다."""

    def __init__(self, *, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _headers(self, *, api: bool) -> dict[str, str]:
        headers = {
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": NAVER_USER_AGENT,
        }
        if api:
            headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "gzip, deflate",
                    "Origin": "https://fin.land.naver.com",
                    "Referer": NAVER_MAP_URL,
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
            )
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,*/*"
        return headers

    def _open(self, url: str, *, api: bool) -> bytes:
        request = urllib.request.Request(url, headers=self._headers(api=api))
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                if response.headers.get("content-encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise NaverComplexLookupError(
                    "네이버 요청 제한으로 단지정보를 불러오지 못했습니다."
                ) from exc
            raise NaverComplexLookupError(
                f"네이버 단지정보 요청에 실패했습니다. (HTTP {exc.code})"
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise NaverComplexLookupError(
                "네이버 단지정보 서버에 연결하지 못했습니다."
            ) from exc

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode(params)
        raw = self._open(f"{NAVER_API_BASE}{path}?{query}", api=True)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NaverComplexLookupError(
                "네이버 단지정보 응답을 해석하지 못했습니다."
            ) from exc
        if payload.get("isSuccess") is not True:
            raise NaverComplexLookupError(
                payload.get("message") or "네이버 단지정보 응답이 올바르지 않습니다."
            )
        return payload.get("result")

    def _bootstrap(self) -> None:
        # 전달받은 개인 쿠키를 저장하지 않고 공개 지도 페이지에서 세션 쿠키를 자동 발급받는다.
        self._open(NAVER_MAP_URL, api=False)

    def _select_candidate(
        self,
        candidates: list[dict[str, Any]],
        *,
        name: str,
        latitude: Decimal,
        longitude: Decimal,
    ) -> dict[str, Any]:
        requested_name = _normalize_complex_name(name)
        ranked: list[tuple[int, float, dict[str, Any]]] = []
        for candidate in candidates:
            candidate_name = _normalize_complex_name(candidate.get("complexName"))
            if not requested_name or not candidate_name:
                continue
            if requested_name == candidate_name:
                name_score = 100
            elif requested_name in candidate_name or candidate_name in requested_name:
                name_score = 80
            else:
                continue
            coordinates = candidate.get("coordinates") or {}
            try:
                distance = _distance_km(
                    float(latitude),
                    float(longitude),
                    float(coordinates["yCoordinate"]),
                    float(coordinates["xCoordinate"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if distance > 3.0:
                continue
            distance_score = 50 if distance <= 1.0 else 20
            ranked.append((name_score + distance_score, distance, candidate))
        if not ranked:
            raise NaverComplexLookupError(
                "단지명과 위치가 일치하는 네이버 단지를 찾지 못했습니다."
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][2]

    @staticmethod
    def _heating_label(complex_data: dict[str, Any]) -> str | None:
        values = complex_data.get("heatingAndCoolingInfo") or {}
        labels = [
            HEATING_SYSTEM_LABELS.get(values.get("heatingAndCoolingSystemType")),
            HEATING_ENERGY_LABELS.get(values.get("heatingEnergyType")),
        ]
        return ", ".join(label for label in labels if label) or None

    @staticmethod
    def _apartment_types(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        apartment_types = []
        for sort_order, row in enumerate(rows):
            supply_area = row.get("supplyArea")
            name_type = str(row.get("nameType") or "").strip()
            pyeong_label = None
            if supply_area is not None:
                pyeong_label = f"{int(float(supply_area) / 3.305785)}{name_type}"
            floor_plans = row.get("floorPlanUrls") or {}
            apartment_types.append(
                {
                    "type_name": str(row.get("name") or "").strip() or None,
                    "pyeong_label": pyeong_label,
                    "supply_area_m2": row.get("supplyArea"),
                    "exclusive_area_m2": row.get("exclusiveArea"),
                    "room_count": row.get("roomCount"),
                    "bathroom_count": row.get("bathRoomCount"),
                    "has_basic_layout": _has_floor_plan_variant(
                        floor_plans.get("BASE")
                    ),
                    "has_expanded_layout": _has_floor_plan_variant(
                        floor_plans.get("EXPN")
                    ),
                    "sort_order": sort_order,
                }
            )
        return apartment_types

    def search_by_keyword(self, keyword: str, *, page: int = 0) -> dict[str, Any]:
        """v2.5.1(2026-08-22): "네이버 검색 기반 이중검사" 기능 -- 시군구
        이름으로 검색해 그 지역 단지 목록을 페이지 단위로 돌려준다(한
        페이지 5건, `hasNextPage`/`totalCount` 포함). `list_complexes_by_cortarno`
        (법정동 코드 훑기)와는 다른 진입점이라, 둘의 결과를 대조하면
        한쪽이 놓친 단지를 찾아낼 수 있다(실제로 분양중 아파트(B01)
        누락을 이 방식으로 찾음, V2.5.0_PLAN.md 참고). `list` 항목의
        `type` 필드는 `list_complexes_by_cortarno`의 `hscpTypeCd`와
        동일한 코드 체계(A01/A02/B01/B02)."""
        self._bootstrap()
        return self._get_json(
            "/search/autocomplete/apartmentComplexes",
            {"keyword": keyword, "page": page},
        ) or {}

    def lookup(
        self,
        *,
        name: str,
        latitude: Decimal,
        longitude: Decimal,
    ) -> dict[str, Any]:
        self._bootstrap()
        candidates: list[dict[str, Any]] = []
        # 카카오 단지명에 붙은 '아파트' 때문에 검색 결과가 0건이면 정규화한 이름으로 한 번만 재조회한다.
        keywords = [name]
        normalized_name = _normalize_complex_name(name)
        if normalized_name and normalized_name != name:
            keywords.append(normalized_name)
        for keyword in keywords:
            search = self._get_json(
                "/search/autocomplete/apartmentComplexes",
                {"keyword": keyword, "page": 0},
            ) or {}
            candidates = search.get("list") or []
            if candidates:
                break
        candidate = self._select_candidate(
            candidates,
            name=name,
            latitude=latitude,
            longitude=longitude,
        )
        return self._build_result(
            complex_number=int(candidate["complexNumber"]),
            fallback_name=candidate.get("complexName") or name,
            fallback_latitude=latitude,
            fallback_longitude=longitude,
        )

    def lookup_by_complex_number(
        self,
        *,
        complex_number: int,
        name: str | None = None,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
        is_officetel: bool | None = None,
    ) -> dict[str, Any]:
        """v2.5.1: 시군구 기준 자동수집 전용 -- 이름/좌표로 후보를 찾는
        `lookup()`과 달리, 네이버부동산 지역별 단지목록(m.land.naver.com
        complexListByCortarNo)에서 이미 확보한 단지번호로 바로 상세정보를
        조회한다(검색·매칭 단계가 없어 더 정확하고 빠르다). 좌표는 상세
        응답에 없을 때만 쓸 대체값으로 넘긴다. `is_officetel`은 단지목록
        API의 hscpTypeCd(A01=아파트/A02=오피스텔)에서 이미 정확히
        확인된 값을 그대로 넘겨받아 결과의 complex_type에 담는다 --
        `/complex` 상세 API 자체에는 이 구분이 따로 없다.
        V2.5.0_PLAN.md 참고."""
        self._bootstrap()
        return self._build_result(
            complex_number=complex_number,
            fallback_name=name,
            fallback_latitude=latitude,
            fallback_longitude=longitude,
            is_officetel=is_officetel,
        )

    def _build_result(
        self,
        *,
        complex_number: int,
        fallback_name: str | None,
        fallback_latitude: Decimal | None,
        fallback_longitude: Decimal | None,
        is_officetel: bool | None = None,
    ) -> dict[str, Any]:
        complex_data = self._get_json(
            "/complex", {"complexNumber": complex_number}
        ) or {}
        pyeong_rows = self._get_json(
            "/complex/pyeongList", {"complexNumber": complex_number}
        ) or []
        address = complex_data.get("address") or {}
        coordinates = complex_data.get("coordinates") or {}
        approval_date = str(complex_data.get("useApprovalDate") or "")
        parking = complex_data.get("parkingInfo") or {}
        latitude = coordinates.get("yCoordinate") or fallback_latitude
        longitude = coordinates.get("xCoordinate") or fallback_longitude
        complex_type = (
            "officetel" if is_officetel is True
            else "apartment" if is_officetel is False
            else None
        )
        return {
            "naver_complex_number": complex_number,
            "complex_type": complex_type,
            "name": complex_data.get("name") or fallback_name,
            "sido": address.get("city"),
            "sigungu": address.get("division"),
            "eupmyeondong": address.get("sector"),
            "road_address": " ".join(
                item
                for item in (
                    address.get("city"),
                    address.get("division"),
                    address.get("roadName"),
                )
                if item
            ) or None,
            "jibun_address": " ".join(
                item
                for item in (
                    address.get("city"),
                    address.get("division"),
                    address.get("sector"),
                    address.get("jibun"),
                )
                if item
            ) or None,
            "latitude": latitude,
            "longitude": longitude,
            "completion_year": int(approval_date[:4])
            if len(approval_date) >= 4 and approval_date[:4].isdigit()
            else None,
            "household_count": complex_data.get("totalHouseholdNumber"),
            "building_count": complex_data.get("dongCount"),
            "parking_count": parking.get("totalParkingCount"),
            "heating_type": self._heating_label(complex_data),
            "builder_name": complex_data.get("constructionCompany"),
            "apartment_types": self._apartment_types(pyeong_rows),
        }


# v2.5.1: 시군구 기준 단지 자동수집 1단계 -- 법정동(cortarNo) 하나 안에
# 있는 아파트/오피스텔 단지 목록(단지번호·이름·좌표)을 가져온다. 이
# 호출은 세션 쿠키가 필요 없어 클래스 인스턴스 없이 매번 새로 요청해도
# 무방하다(호출 빈도가 법정동 개수만큼이라 원래도 많지 않음).
def list_complexes_by_cortarno(cortar_no: str, *, timeout_seconds: int = 10) -> list[dict[str, Any]]:
    url = f"{MLAND_API_BASE}/complex/ajax/complexListByCortarNo?cortarNo={cortar_no}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "User-Agent": MLAND_USER_AGENT,
            "Referer": "https://m.land.naver.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise NaverComplexLookupError(
            f"네이버 단지목록 요청에 실패했습니다. (HTTP {exc.code})"
        ) from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise NaverComplexLookupError("네이버 단지목록 서버에 연결하지 못했습니다.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NaverComplexLookupError("네이버 단지목록 응답을 해석하지 못했습니다.") from exc
    rows = payload.get("result") or []
    complexes = []
    for row in rows:
        try:
            complex_number = int(row["hscpNo"])
        except (KeyError, TypeError, ValueError):
            continue
        type_code = str(row.get("hscpTypeCd") or "")
        # 2026-08-22: hscpTypeNm(한글 라벨) 실측으로 확인된 코드들 --
        # A01=아파트, A02=오피스텔(둘 다 완공), A04=재건축(과천 주공
        # 단지처럼 재건축 대상이지만 여전히 실제 존재/거주 중인 아파트),
        # B01=아파트 분양권(분양중/공사중, 완공 전). 전부 "실제 있거나
        # 곧 있을 아파트/오피스텔"이라 사용자 지시로 포함시킴(CLAUDE.md
        # 4번 원칙 -- 완공·입주 시점에 바로 쓸 수 있게 미리 등록).
        # B02(오피스텔 분양권으로 추정, 아직 실측된 사례는 없지만 A02의
        # B0x 대응으로 미리 허용)도 같은 이유.
        #
        # 이 목록이 네이버의 전체 코드 체계를 다 아는 건 아니다 -- 아직
        # 못 본 코드가 더 있을 수 있는데, 그건 "네이버 검색 기반
        # 이중검사"(`complex_region_import/worker.py`의
        # `_run_cross_check_job`)가 실행할 때마다 "확인 필요" 후보로
        # 잡아준다(실제로 A04도 이 방식으로 찾음). 새 코드가 실제
        # 아파트/오피스텔로 확인되면 여기 목록에 추가하면 된다 --
        # 무조건 다 받지 않고 확인된 것만 허용하는 이유는 상가/상업시설
        # 같은 무관한 매물 유형이 이 API에 섞여 들어올 위험을 피하기
        # 위함.
        if type_code not in {"A01", "A02", "A04", "B01", "B02"}:
            continue
        try:
            latitude = Decimal(str(row["lat"]))
            longitude = Decimal(str(row["lng"]))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            latitude = None
            longitude = None
        complexes.append(
            {
                "complex_number": complex_number,
                "name": str(row.get("hscpNm") or "").strip(),
                "is_officetel": type_code in ("A02", "B02"),
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return complexes
