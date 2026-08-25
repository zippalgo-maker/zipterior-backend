"""대량등록 완료 후 자동으로 이어지는 title/본문 텍스트 마이닝
(2026-08-22, 사용자 지시: "일단 다 등록해두고... 대량등록 완료 시
자동으로 이어진" -- CLAUDE.md 4번 원칙, 서버가 스스로 처리).

structured 필드(street_address/apartment_name/area_type 등)가 비어서
단지·타입을 못 찾은 포트폴리오를 대상으로, title에서 단지명/평형/
타입코드 후보를 뽑아 기존에 이미 검증된 안전한 함수들
(`search_complex_by_building_name`, `resolve_type_for_import`,
`_ensure_portfolio_complex`)로 다시 시도한다. 이 모듈은 후보를
"뽑기"만 하고, 실제 검색·검증·저장은 전부 기존 함수를 그대로
재사용한다(새 매칭 로직을 여기서 재구현하지 않음).

**중요(2026-08-22 실사용 검증에서 발견한 사고)**: 이름만 흔하고
지역 정보가 없는 후보(예: "현대아파트")를 그대로 카카오 검색에
넣으면, 찾아낸 결과 자체는 맞아도 그걸 기존 단지와 대조하는
`find_complex_for_import`가 지역을 안 보고 이름만으로 다른 도시의
동명 단지에 잘못 연결한 사고가 실제로 있었다(포트폴리오 #1390,
남양주 "현대아파트"가 서울 동작구 "현대아파트"에 잘못 연결됨).
`find_complex_for_import`에 sigungu 파라미터를 추가해 근본 원인은
고쳤지만(2026-08-22), 이 모듈에서도 카카오 검색 결과의 지역이
title에 있는 다른 지역명과 충돌하면 애초에 후보로 채택하지 않는
2중 안전장치를 유지한다."""

import logging
import re
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.admin.kakao_complex_client import (
    KakaoComplexLookupError,
    search_complex_by_building_name,
)
from app.modules.admin.portfolio_service import AdminPortfolioService
from app.modules.bulk_import import repository
from app.modules.bulk_import.worker import _ensure_portfolio_complex

logger = logging.getLogger(__name__)

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
_SEGMENT_SPLIT_RE = re.compile(r"[\-:|·*“”‘’\"',!_/]+")
_BRACKET_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")
_PYEONG_TAIL_RE = re.compile(r"\d+\s*(?:평형?|py|제곱미터|㎡|평대)\s*$", re.IGNORECASE)
_PYEONG_RE = re.compile(r"(\d{2,3})\s*(?:평형|평대|평)")
_PY_RE = re.compile(r"(\d{2,3})\s*PY", re.IGNORECASE)
_SQM_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*(?:㎡|m2|제곱미터)")
_REGION_MENTION_RE = re.compile(r"(시|구|군|동|읍|면)\b")


def extract_title_building_candidates(title: str | None) -> list[str]:
    """title을 강한 구분자로 잘라 단지명 후보 문자열 목록을 만든다.
    완벽한 추출이 목표가 아니다 -- 잘못된 후보는
    `search_complex_by_building_name`의 "아파트" 카테고리 필터가
    자연히 걸러내므로, 여기서는 그럴듯한 조각을 넉넉히 만드는 것만
    신경 쓴다."""
    if not title:
        return []
    text_value = _EMOJI_RE.sub(" ", title)
    segments = _SEGMENT_SPLIT_RE.split(text_value)
    out: list[str] = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) < 3:
            continue
        seg = _BRACKET_PREFIX_RE.sub("", seg)
        seg = _PYEONG_TAIL_RE.sub("", seg).strip()
        if seg and seg not in out and len(seg) >= 3:
            out.append(seg)
    return out


def extract_pyeong_from_text(text_value: str | None) -> int | None:
    if not text_value:
        return None
    m = _PYEONG_RE.search(text_value)
    if m:
        return int(m.group(1))
    m = _PY_RE.search(text_value)
    if m:
        return int(m.group(1))
    m = _SQM_RE.search(text_value)
    if m:
        return round(float(m.group(1)) / 3.3058)
    return None


def extract_type_codes_from_text(text_value: str | None) -> list[str]:
    if not text_value:
        return []
    return re.findall(r"\b(\d{2,3}[A-Za-z])\b", text_value)


def _region_conflicts(kakao_sigungu: str | None, title: str) -> bool:
    """카카오가 찾은 시군구가 title에 언급된 다른 지역명과 충돌하는지
    본다. title에 지역 표현이 아예 없으면(설명뿐인 제목) 검증할 게
    없으므로 통과시킨다 -- 이 경우의 안전장치는
    `find_complex_for_import`의 sigungu 일치 요구가 대신 맡는다."""
    if not _REGION_MENTION_RE.search(title):
        return False
    sigungu_key = re.sub(r"(시|구|군)$", "", kakao_sigungu or "")
    if not sigungu_key:
        return False
    return sigungu_key not in title.replace("시", "").replace("구", "").replace("군", "")


def mine_unresolved_portfolios_for_job(
    job_id: int, *, admin_user_id: int
) -> dict[str, Any]:
    """job_id로 등록된 포트폴리오 중 complex_id 또는 apartment_type_id가
    비어있는 것만 골라 title 마이닝을 시도한다. 기존 값은 절대
    덮어쓰지 않는다(additive-only). 실제 저장은 관리자 화면이 쓰는
    것과 동일한 `AdminPortfolioService.assign_complex()`를 그대로
    호출한다(감사로그도 정상 기록됨)."""
    with SessionLocal() as session:
        rows = session.execute(text("""
            SELECT p.id AS portfolio_id, p.complex_id, p.apartment_type_id,
                   r.record_key, r.payload
            FROM portfolios p
            JOIN bulk_import_records r ON r.job_id=:job_id AND r.target_id=p.id
            WHERE p.deleted_at IS NULL
              AND (p.complex_id IS NULL OR p.apartment_type_id IS NULL)
            ORDER BY p.id
        """), {"job_id": job_id}).mappings().all()

    stats = {
        "candidates_checked": len(rows),
        "complex_mined": 0,
        "type_mined": 0,
        "kakao_calls": 0,
    }
    if not rows:
        return stats

    for row in rows:
        payload = row["payload"] or {}
        title = str(payload.get("title") or "").strip()
        if not title:
            continue

        complex_id = row["complex_id"]
        apartment_type_id = row["apartment_type_id"]
        changed = False

        if complex_id is None:
            for candidate in extract_title_building_candidates(title):
                stats["kakao_calls"] += 1
                try:
                    kakao_result = search_complex_by_building_name(candidate)
                except KakaoComplexLookupError:
                    kakao_result = None
                if not kakao_result:
                    continue
                if _region_conflicts(kakao_result.get("sigungu"), title):
                    continue
                item = {
                    "apartment_name": None,
                    "street_address": None,
                    "area_type": None,
                    "area_type_structured": None,
                    "area_type_text_detected": None,
                    "area_id": None,
                    "real_area_pyeong": extract_pyeong_from_text(title),
                    "area_pyeong": None,
                }
                new_complex_id, _created, _naver = _ensure_portfolio_complex(
                    job={"id": job_id, "requested_by": admin_user_id},
                    item=item,
                    resolution=kakao_result,
                )
                if not new_complex_id:
                    continue
                complex_id = new_complex_id
                changed = True
                stats["complex_mined"] += 1
                logger.info(
                    "title 마이닝으로 단지 매칭: job_id=%s portfolio_id=%s "
                    "candidate=%s matched=%s",
                    job_id, row["portfolio_id"], candidate, kakao_result.get("name"),
                )
                break

        if complex_id and apartment_type_id is None:
            mined_types = extract_type_codes_from_text(title)
            mined_pyeong = extract_pyeong_from_text(title)
            probe_item = {
                "area_id": None,
                "area_type_structured": None,
                "area_type": mined_types[0] if len(mined_types) == 1 else None,
                "area_type_text_detected": None,
                "real_area_pyeong": mined_pyeong,
                "area_pyeong": None,
            }
            with SessionLocal() as lookup_session:
                resolved_type_id, _ambiguous = repository.resolve_type_for_import(
                    lookup_session, complex_id=complex_id, item=probe_item
                )
            if resolved_type_id:
                apartment_type_id = resolved_type_id
                changed = True
                stats["type_mined"] += 1

        if not changed:
            continue
        with SessionLocal() as session:
            AdminPortfolioService.assign_complex(
                session,
                portfolio_id=row["portfolio_id"],
                admin_user_id=admin_user_id,
                complex_id=complex_id,
                apartment_type_id=apartment_type_id,
            )

    logger.info(
        "대량등록 후 title 마이닝 완료: job_id=%s stats=%s", job_id, stats
    )
    return stats
