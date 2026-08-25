"""Portfolio-level shared constants.

CONSTRUCTION_SCOPE_OPTIONS는 `portfolios.construction_scope` 컬럼에 들어갈
수 있는 정답 목록의 단일 기준(single source of truth)이다. 아래 세 곳이
전부 이 목록 하나만 봐야 한다 -- 목록을 추가/변경하면 세 곳을 같이 고친다.

1. 개별등록 폼(`company-dashboard.html`의 `#portfolioForm` 안 `select[name=scope]`)
   -- 업체가 직접 고르는 선택지.
2. `bulk_import.worker`가 호출하는 `classify_construction_scope()` -- 크롤링
   원본의 자유 텍스트(`expertise` 필드)를 이 중 하나로 분류해서 저장.
3. 관리자 "포트폴리오 관리" 화면의 "공사유형" 필터(`admin-dashboard.html`).

2026-08-22, construction_scope 불일치 문제(개별등록은 3개 고정 선택지인데
일괄등록은 크롤링 원본 텍스트를 검증 없이 그대로 저장해 "리모델링"/"건축"
같은 목록에 없는 값이 87%를 차지하던 문제) 수정하며 처음 정리함. 자세한
경위는 V2.5.0_PLAN.md의 "construction_scope 개별등록/일괄등록 값 체계
불일치 수정" 절 참고.
"""

CONSTRUCTION_SCOPE_OPTIONS: tuple[str, ...] = (
    "전체공사",
    "주방·거실",
    "부분공사",
    "홈스타일링",
)

_DEFAULT_SCOPE = "전체공사"


def classify_construction_scope(raw_expertise: str | None) -> str | None:
    """크롤링 원본의 `expertise` 자유 텍스트를 CONSTRUCTION_SCOPE_OPTIONS 중
    하나로 분류한다. 값이 비어 있으면 None(미입력)을 그대로 유지 -- 억지로
    기본값을 채우지 않는다.

    이 함수가 오늘의집 원본이 쓰는 모든 표현을 다 아는 건 아니다(2026-08-22
    기준 실제로 관측된 값은 리모델링/부분공사/홈스타일링/건축 4개뿐). 새로운
    표현이 들어오면 정확히 일치하는 게 없을 때 아래 키워드 규칙으로
    분류하고, 그래도 못 알아보면 `전체공사`로 떨어진다(부분공사로 잘못
    분류해 필터에서 아예 안 보이는 것보다, 가장 큰 범주로 잡히는 쪽이
    안전하다는 판단). 새 원본 표현이 자주 보이면 이 함수에 규칙을
    추가한다.
    """
    text = (raw_expertise or "").strip()
    if not text:
        return None

    # 1) 원본 표현이 이미 정확히 일치하는 경우
    if text in CONSTRUCTION_SCOPE_OPTIONS:
        return text

    # 2) 지금까지 실제로 관측된 원본 표현의 직접 매핑
    exact_map = {
        "리모델링": "전체공사",
        "전체 리모델링": "전체공사",
        "건축": "전체공사",  # 신축 단독주택 등 -- 범주상 가장 가까운 값
    }
    if text in exact_map:
        return exact_map[text]

    # 3) 키워드 기반 fallback (아직 안 본 표현 대비)
    if "홈스타일링" in text or "스타일링" in text:
        return "홈스타일링"
    if "주방" in text and "거실" in text:
        return "주방·거실"
    if "부분" in text:
        return "부분공사"

    return _DEFAULT_SCOPE
