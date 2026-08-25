"""v2.5.1: 시군구 기준 네이버부동산 단지 자동수집 기능의 첫 단계 --
관리자가 입력한 시군구 이름 안에 있는 법정동(읍면동) 코드 목록을 공공데이터
포털(data.go.kr) "행정안전부_행정표준코드_법정동코드" API로 조회한다.

이 API가 돌려주는 10자리 `region_cd`가 네이버부동산이 쓰는 `cortarNo`와
동일하다는 것을 실제 호출로 확인했다(예: region_cd=4113510300 = 경기도
성남시 분당구 정자동 -> 네이버 complexListByCortarNo에 그대로 넣으면
정자동 단지 목록이 나옴). V2.5.0_PLAN.md 참고."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings

STANREGINCD_BASE = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
_TIMEOUT_SECONDS = 10


class LegalDongLookupError(ValueError):
    pass


def _request(params: dict[str, str]) -> dict[str, Any]:
    if not settings.data_go_kr_stanregincd_key:
        raise LegalDongLookupError(
            "DATA_GO_KR_STANREGINCD_KEY가 설정되어 있지 않습니다."
        )
    # ServiceKey는 포털에서 이미 URL 인코딩된 값을 그대로 쓴다 -- 여기서
    # 다시 urlencode하면 %가 이중 인코딩되어 인증이 깨진다.
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{STANREGINCD_BASE}?ServiceKey={settings.data_go_kr_stanregincd_key}&{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            # 2026-08-22: 이 API는 정식 인증키를 쓰는 공공데이터 API라
            # 차단 이력은 없었지만, User-Agent가 아예 없으면(파이썬
            # 기본값) 일부 서버/방화벽이 정상 클라이언트로 안 봐줄 수
            # 있어 다른 외부 API 호출과 동일하게 명시적으로 채운다.
            "User-Agent": "Zipterior/1.0 (+https://zipterior.kr)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise LegalDongLookupError(
            f"법정동코드 API 호출 실패({exc.code}): {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LegalDongLookupError(f"법정동코드 API 연결 실패: {exc.reason}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegalDongLookupError("법정동코드 API 응답을 해석하지 못했습니다.") from exc
    # 인증키 오류/트래픽 초과 등은 data.go.kr 공통 오류 포맷(cmmMsgHeader)
    # 이나 StanReginCd가 리스트가 아닌 형태(단일 dict)로 온다 -- 두 경우
    # 모두 정상 응답과 모양이 달라서 이 자리에서 걸러낸다.
    error_header = payload.get("cmmMsgHeader")
    if error_header:
        raise LegalDongLookupError(
            error_header.get("errMsg")
            or error_header.get("returnAuthMsg")
            or "법정동코드 API 인증에 실패했습니다."
        )
    if not isinstance(payload.get("StanReginCd"), list):
        raise LegalDongLookupError("법정동코드 API 응답 형식이 예상과 다릅니다.")
    return payload


def list_dong_codes(sigungu_query: str, *, max_rows: int = 500) -> list[dict[str, Any]]:
    """시군구 이름(예: '성남시 분당구', '경기도 성남시 분당구')으로 검색해
    그 안에 속한 법정동(읍면동) 목록을 [{code, name, dong_name}] 형태로
    돌려준다. 시군구 자체를 가리키는 요약 행(umd_cd='000')은 제외한다."""
    name = str(sigungu_query or "").strip()
    if not name:
        raise LegalDongLookupError("시군구 이름을 입력해 주세요.")
    payload = _request(
        {
            "type": "json",
            "pageNo": "1",
            "numOfRows": str(max_rows),
            "locatadd_nm": urllib.parse.quote(name),
        }
    )
    entries = payload.get("StanReginCd") or []
    rows: list[dict[str, Any]] = []
    for entry in entries:
        rows.extend(entry.get("row") or [])
    dong_codes = [
        {
            "code": str(row.get("region_cd") or ""),
            "name": str(row.get("locatadd_nm") or ""),
            "dong_name": str(row.get("locallow_nm") or ""),
        }
        for row in rows
        if str(row.get("umd_cd") or "000") != "000" and row.get("region_cd")
    ]
    if not dong_codes:
        raise LegalDongLookupError(
            f'"{name}"에 해당하는 법정동을 찾지 못했습니다. '
            "시군구 이름(예: '성남시 분당구')을 확인해 주세요."
        )
    return dong_codes
