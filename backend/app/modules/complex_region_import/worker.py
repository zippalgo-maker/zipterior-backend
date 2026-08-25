"""v2.5.1: 시군구 기준 네이버부동산 단지 자동수집 백그라운드 워커.

흐름: 시군구 이름 -> legal_dong_client로 법정동(cortarNo) 목록 조회 ->
naver_complex_client.list_complexes_by_cortarno로 법정동마다 단지목록
수집(단지번호 기준 중복 제거) -> 단지마다 lookup_by_complex_number로
상세조회 -> AdminComplexService로 저장(기존 정규화 이름+주소 unique
제약이 중복을 자연스럽게 걸러줌). bulk_import/worker.py와 같은
"단일 프로세스 내 백그라운드 스레드 + DB 폴링" 패턴을 그대로 따른다.
V2.5.0_PLAN.md 참고."""

import logging
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.admin.complex_service import (
    AdminComplexDuplicateError,
    AdminComplexService,
)
from app.modules.admin.legal_dong_client import LegalDongLookupError, list_dong_codes
from app.modules.admin.naver_complex_client import (
    NaverComplexClient,
    NaverComplexLookupError,
    _normalize_complex_name,
    list_complexes_by_cortarno,
)
from app.modules.complex_region_import import repository

logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_started = False

# 네이버에 부담을 주지 않기 위한 호출 간격 (2026-08-22 개정: 실측으로
# 확인된 사고 -- 항상 정확히 0.4초 간격으로만 두드리면 그 규칙성
# 자체가 "기계적 트래픽"으로 보여 남용(abuse) 탐지에 걸리기 쉽다.
# 양평군 자동수집이 실제로 이렇게 차단당해서 122개 법정동 중
# 121개가 조용히 실패한 사고가 있었음(V2.5.0_PLAN.md 참고). 사람이
# 화면을 넘겨보듯 매번 다른 간격으로 쉬고, 가끔은 더 길게 멈춘다.
_REQUEST_DELAY_RANGE = (0.6, 1.6)
_LONG_PAUSE_EVERY = 20  # 이 정도 호출마다 한 번은 사람이 딴짓하듯 더 오래 쉼
_LONG_PAUSE_RANGE = (3.0, 6.0)
_RETRY_BACKOFF_SECONDS = (2.0, 5.0, 10.0)  # 실패 시 재시도 간격(초), 매번 더 길어짐

T = TypeVar("T")


def _polite_sleep(call_index: int) -> None:
    time.sleep(random.uniform(*_REQUEST_DELAY_RANGE))
    if call_index > 0 and call_index % _LONG_PAUSE_EVERY == 0:
        time.sleep(random.uniform(*_LONG_PAUSE_RANGE))


def _call_with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """일시적인 실패(네트워크 순단, 짧은 과부하 등)는 재시도로 흡수하고
    진짜 지속적인 차단만 호출부에 전달한다 -- 그래야 2단계의 "연속
    실패 N회면 차단 의심" 판정이 우연한 한두 번 실패에 과민반응하지
    않고 진짜 차단에만 반응한다."""
    last_exc: NaverComplexLookupError | None = None
    for backoff in (0.0, *_RETRY_BACKOFF_SECONDS):
        if backoff:
            time.sleep(backoff + random.uniform(0, 1.5))
        try:
            return fn(*args, **kwargs)
        except NaverComplexLookupError as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _utcnow_iso(*, offset_minutes: float = 0.0) -> str:
    """차단 감지/대기/재개 기록용 타임스탬프. `summary`(jsonb)에 그대로
    저장되므로 사람이 읽기 쉬운 ISO 문자열로 남긴다."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()


def _job_cancelled(job_id: int) -> bool:
    with SessionLocal() as session:
        return repository.is_cancelled(session, job_id=job_id)


def _finish_job(
    job_id: int,
    *,
    status: str,
    summary_updates: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    with SessionLocal() as session:
        job = repository.get_job(session, job_id=job_id)
        summary = dict((job or {}).get("summary") or {})
        if summary_updates:
            summary.update(summary_updates)
        repository.update_job(
            session,
            job_id=job_id,
            changes={
                "status": status,
                "summary": summary,
                "error_message": error_message,
            },
        )
        session.execute(
            text(
                "UPDATE complex_region_import_jobs SET completed_at=NOW() "
                "WHERE id=:job_id"
            ),
            {"job_id": job_id},
        )
        session.commit()


def _values_from_detail(detail: dict[str, Any]) -> dict[str, Any] | None:
    name = detail.get("name")
    road_address = detail.get("road_address")
    latitude = detail.get("latitude")
    longitude = detail.get("longitude")
    if not name or not road_address or latitude is None or longitude is None:
        return None
    return {
        "name": name,
        "complex_type": detail.get("complex_type"),
        "sido": detail.get("sido"),
        "sigungu": detail.get("sigungu"),
        "eupmyeondong": detail.get("eupmyeondong"),
        "road_address": road_address,
        "jibun_address": detail.get("jibun_address"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "completion_year": detail.get("completion_year"),
        "household_count": detail.get("household_count"),
        "building_count": detail.get("building_count"),
        "parking_count": detail.get("parking_count"),
        "heating_type": detail.get("heating_type"),
        "builder_name": detail.get("builder_name"),
    }


def _run_job(job: dict[str, Any]) -> None:
    job_id = job["id"]
    with SessionLocal() as session:
        repository.update_job(
            session, job_id=job_id, changes={"status": "running", "error_message": None}
        )
        session.execute(
            text(
                "UPDATE complex_region_import_jobs "
                "SET started_at=COALESCE(started_at, NOW()) WHERE id=:job_id"
            ),
            {"job_id": job_id},
        )
        session.commit()

    if job.get("job_kind") == "cross_check":
        _run_cross_check_job(job)
        return

    # 1단계: 시군구 -> 법정동(cortarNo) 목록.
    # 2026-08-22: "실패한 법정동만 재시도" job은 dong_codes_filter에
    # 원래 job의 summary.dong_results에서 이미 확보해둔 code/name/
    # dong_name을 그대로 담아오므로, 정부 법정동코드 API를 또 부를
    # 필요가 없다(이미 유효성이 검증된 코드라 재조회가 의미 없음).
    dong_codes_filter = job.get("dong_codes_filter")
    if dong_codes_filter:
        dong_codes = dong_codes_filter
    else:
        try:
            dong_codes = list_dong_codes(job["sigungu_query"])
        except LegalDongLookupError as exc:
            _finish_job(job_id, status="failed", error_message=str(exc))
            return

    with SessionLocal() as session:
        repository.update_job(
            session, job_id=job_id, changes={"total_dong_count": len(dong_codes)}
        )
        session.commit()

    # 2단계: 법정동마다 단지 목록 수집, 단지번호 기준 중복 제거.
    # 실측 확인된 문제(2026-08-22, 양평군 자동수집이 122개 법정동을 다
    # 돌고도 단지 1건만 나온 사고): 네이버가 이 목록 조회 엔드포인트를
    # 남용(abuse)으로 판단해 `/error/abuse`로 리다이렉트하기 시작하면,
    # 기존 코드는 이걸 그냥 "이 법정동엔 단지가 없나보다"로 조용히
    # 넘어가서 -- 진행률은 100%인데 결과만 텅 빈 job이 "완료"로
    # 끝나버렸다(관리자가 실패를 알 방법이 전혀 없었음).
    #
    # 사용자 지시(2026-08-22, 같은 날 이어서): "차단당한 거면 10~15분
    # 쉬었다가 다시 접속하면 진행 가능하니 그것도 적용하고, 차단->재시작
    # ->완료를 기록해서 확인 가능하게 해라." (UA 로테이션 등 탐지 회피는
    # 명시적으로 적용 안 함 -- 요청 속도를 실제로 낮추는 것과 차단
    # 메커니즘을 속이는 것은 다른 문제라고 판단, 사용자에게도 설명함.)
    #
    # 동작: 연속 실패가 일정 횟수를 넘으면(차단 의심) 그 자리서 완전히
    # 포기하지 않고, 10~15분(무작위) 대기 후 실패했던 지점부터 자동으로
    # 이어서 재시도한다(최대 2회까지). 대기/재개 시각을 전부
    # summary["block_pauses"]에 남겨서 "차단→대기→재개→완료"를 나중에
    # 그대로 확인할 수 있게 한다.
    _CONSECUTIVE_FAILURE_LIMIT = 8
    _MAX_BLOCK_RETRIES = 2
    _BLOCK_COOLDOWN_MINUTES_RANGE = (10.0, 15.0)
    # 사용자 지시(같은 날 이어서): "어떤 읍면동에 아파트 몇 개 어떻게
    # 가져왔는지 확인할 수 있도록" -- 법정동 하나 처리할 때마다 그
    # 법정동이 새로 기여한 단지 수를 dong_results에 남긴다(단지번호
    # 기준 전역 중복제거(seen)는 그대로 유지하되, "이 동에서 처음
    # 발견된 것"만 그 동의 기여로 집계).
    seen: dict[int, dict[str, Any]] = {}
    dong_results: list[dict[str, Any]] = []
    failed_dong_names: list[str] = []
    block_pauses: list[dict[str, Any]] = []
    start_index = 0
    block_retry_count = 0

    while start_index < len(dong_codes):
        consecutive_failures = 0
        blocked_mid_sweep = False
        for index in range(start_index, len(dong_codes)):
            dong = dong_codes[index]
            if _job_cancelled(job_id):
                _finish_job(job_id, status="cancelled")
                return
            try:
                complexes = _call_with_retry(list_complexes_by_cortarno, dong["code"])
                new_count = 0
                for item in complexes:
                    if item["complex_number"] not in seen:
                        new_count += 1
                    seen.setdefault(item["complex_number"], item)
                dong_results.append({
                    "code": dong["code"],
                    "name": dong["name"],
                    "dong_name": dong["dong_name"],
                    "status": "ok",
                    "found_count": len(complexes),
                    "new_count": new_count,
                })
                consecutive_failures = 0
            except NaverComplexLookupError as exc:
                logger.warning(
                    "법정동 단지목록 조회 실패",
                    exc_info=True,
                    extra={"job_id": job_id, "dong_code": dong["code"]},
                )
                dong_results.append({
                    "code": dong["code"],
                    "name": dong["name"],
                    "dong_name": dong["dong_name"],
                    "status": "failed",
                    "found_count": 0,
                    "new_count": 0,
                    # 2026-08-22: 실패 사유를 사람이 읽을 수 있게 남긴다
                    # (예: "네이버 단지목록 요청에 실패했습니다. (HTTP 307)"
                    # -- 네이버 abuse 차단 신호). "그 동에 진짜 아파트가
                    # 없는" 경우는 이 분기를 안 타고 status="ok",
                    # found_count=0으로 별도 기록되므로 여기 남는 실패는
                    # 전부 API 호출 자체가 실패한 경우다.
                    "error": str(exc)[:300],
                })
                failed_dong_names.append(dong["name"])
                consecutive_failures += 1
                if consecutive_failures >= _CONSECUTIVE_FAILURE_LIMIT:
                    logger.warning(
                        "법정동 조회 연속 실패 %s회 -- 네이버 차단(abuse) 의심: "
                        "job_id=%s dong_index=%s last_error=%s",
                        consecutive_failures, job_id, index, exc,
                    )
                    blocked_mid_sweep = True
                    start_index = index
                    break
            with SessionLocal() as session:
                repository.update_job(
                    session, job_id=job_id, changes={"processed_dong_count": index + 1}
                )
                session.commit()
            _polite_sleep(index)
        else:
            start_index = len(dong_codes)  # break 없이 끝까지 다 돌았음

        if not blocked_mid_sweep:
            break

        block_retry_count += 1
        if block_retry_count > _MAX_BLOCK_RETRIES:
            logger.warning(
                "차단 재시도 한도(%s회) 초과 -- 포기: job_id=%s",
                _MAX_BLOCK_RETRIES, job_id,
            )
            break

        cooldown_minutes = random.uniform(*_BLOCK_COOLDOWN_MINUTES_RANGE)
        paused_at = _utcnow_iso()
        resume_planned_at = _utcnow_iso(offset_minutes=cooldown_minutes)
        pause_record = {
            "attempt": block_retry_count,
            "dong_index": start_index,
            "paused_at": paused_at,
            "resume_planned_at": resume_planned_at,
            "cooldown_minutes": round(cooldown_minutes, 1),
        }
        block_pauses.append(pause_record)
        with SessionLocal() as session:
            repository.update_job(
                session,
                job_id=job_id,
                changes={
                    "error_message": (
                        f"네이버 차단 감지({block_retry_count}/{_MAX_BLOCK_RETRIES}회째) -- "
                        f"약 {round(cooldown_minutes,1)}분 대기 후 법정동 "
                        f"{start_index + 1}/{len(dong_codes)}번째부터 자동 재시도합니다."
                    ),
                    "summary": {
                        **(repository.get_job(session, job_id=job_id) or {}).get("summary", {}),
                        "block_pauses": block_pauses,
                    },
                },
            )
            session.commit()
        logger.warning(
            "차단 감지로 %s분 대기 후 재시도: job_id=%s dong_index=%s",
            round(cooldown_minutes, 1), job_id, start_index,
        )
        cooldown_seconds = cooldown_minutes * 60
        slept = 0.0
        while slept < cooldown_seconds:
            if _job_cancelled(job_id):
                _finish_job(job_id, status="cancelled")
                return
            chunk = min(30.0, cooldown_seconds - slept)
            time.sleep(chunk)
            slept += chunk
        pause_record["resumed_at"] = _utcnow_iso()
        with SessionLocal() as session:
            repository.update_job(
                session,
                job_id=job_id,
                changes={
                    "error_message": None,
                    "summary": {
                        **(repository.get_job(session, job_id=job_id) or {}).get("summary", {}),
                        "block_pauses": block_pauses,
                    },
                },
            )
            session.commit()

    unique_complexes = list(seen.values())
    still_blocked = start_index < len(dong_codes)
    with SessionLocal() as session:
        repository.update_job(
            session,
            job_id=job_id,
            changes={
                "total_count": len(unique_complexes),
                "summary": {
                    **(repository.get_job(session, job_id=job_id) or {}).get("summary", {}),
                    "failed_dong_count": len(failed_dong_names),
                    "failed_dong_names": failed_dong_names[:100],
                    "blocked_early": still_blocked,
                    "block_pauses": block_pauses,
                    "dong_results": dong_results,
                },
            },
        )
        session.commit()

    if still_blocked and not unique_complexes:
        # 재시도(최대 2회)까지 다 해봤는데도 단지를 하나도 못 찾고
        # 차단으로 중단된 경우는 "완료"라고 부르면 안 된다 -- 관리자가
        # 재시도 여부를 바로 판단할 수 있게 failed로.
        _finish_job(
            job_id,
            status="failed",
            error_message=(
                f"법정동 {len(failed_dong_names)}개 연속 조회 실패로 중단됨 "
                f"({block_retry_count}회 대기·재시도 했지만 계속 차단됨 -- "
                "시간을 더 두고 재시도하세요)."
            ),
        )
        return

    if not unique_complexes:
        _finish_job(
            job_id,
            status="completed",
            summary_updates={"message": "해당 시군구에서 단지를 찾지 못했습니다."},
        )
        return

    # 3단계: 단지마다 상세조회 + 저장.
    # v2.5.1: 관리자가 "이 작업으로 어떤 단지가 들어왔는지" 바로 확인하고
    # 필요하면 단지 수정 화면으로 바로 넘어갈 수 있어야 한다는 피드백
    # 반영 -- 성공/중복/실패 각각 이름(+성공은 id까지) summary에 남긴다.
    # V2.5.0_PLAN.md 참고.
    client = NaverComplexClient()
    failed_names: list[str] = []
    duplicate_names: list[str] = []
    created_complexes: list[dict[str, Any]] = []
    for index, item in enumerate(unique_complexes):
        if _job_cancelled(job_id):
            _finish_job(job_id, status="cancelled")
            return

        outcome = "failed"
        try:
            detail = _call_with_retry(
                client.lookup_by_complex_number,
                complex_number=item["complex_number"],
                name=item["name"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                is_officetel=item.get("is_officetel"),
            )
            values = _values_from_detail(detail)
            if values is None:
                failed_names.append(item["name"])
            else:
                apartment_types = [
                    {**type_values, "floor_plan_path": None}
                    for type_values in detail.get("apartment_types") or []
                ]
                with SessionLocal() as session:
                    if apartment_types:
                        created = AdminComplexService.create_complex_with_types(
                            session,
                            admin_user_id=job["requested_by"],
                            values=values,
                            apartment_types=apartment_types,
                        )
                    else:
                        created = AdminComplexService.create_complex(
                            session,
                            admin_user_id=job["requested_by"],
                            values=values,
                        )
                    session.commit()
                created_complexes.append(
                    {
                        "id": created["id"],
                        "name": created.get("name") or values["name"],
                        "complex_type": values.get("complex_type"),
                    }
                )
                outcome = "success"
        except AdminComplexDuplicateError:
            outcome = "duplicate"
            duplicate_names.append(item["name"])
        except NaverComplexLookupError:
            logger.warning(
                "단지 상세조회 실패",
                exc_info=True,
                extra={"job_id": job_id, "complex_number": item["complex_number"]},
            )
            failed_names.append(item["name"])
        except Exception:
            logger.exception(
                "단지 저장 실패",
                extra={"job_id": job_id, "complex_number": item["complex_number"]},
            )
            failed_names.append(item["name"])

        with SessionLocal() as session:
            repository.increment_job_counts(
                session,
                job_id=job_id,
                processed_delta=1,
                success_delta=1 if outcome == "success" else 0,
                duplicate_delta=1 if outcome == "duplicate" else 0,
                failed_delta=1 if outcome == "failed" else 0,
            )
            session.commit()
        _polite_sleep(index)

    with SessionLocal() as session:
        job_now = repository.get_job(session, job_id=job_id)
    # 법정동 목록조회 단계 실패(failed_dong_names)도 완료 상태 판정에
    # 반영한다 -- 예전엔 3단계(단지 상세조회) 실패만 봐서, 2단계에서
    # 법정동을 대거 놓쳐도(예: 양평군 122개 중 121개 실패) 화면엔
    # "완료"로만 보이던 문제를 고침.
    final_status = (
        "completed_with_errors"
        if (job_now or {}).get("failed_count") or failed_dong_names
        else "completed"
    )
    _finish_job(
        job_id,
        status=final_status,
        summary_updates={
            "created_complexes": created_complexes,
            "duplicate_complexes": duplicate_names[:200],
            "failed_complexes": failed_names[:50],
        },
    )


_SIDO_PREFIX_RE = re.compile(
    r"^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|"
    r"세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|"
    r"전라북도|전라남도|경상북도|경상남도|제주특별자치도)\s*"
)


def _bare_sigungu(sigungu_query: str) -> str:
    return _SIDO_PREFIX_RE.sub("", sigungu_query.strip())


def _run_cross_check_job(job: dict[str, Any]) -> None:
    """v2.5.1(2026-08-22, 사용자 지시 "이중검사 시스템 만들어"): 법정동
    훑기(sweep, `_run_job`)와는 다른 진입점 -- 네이버 통합검색
    (`fin.land.naver.com`, 오늘 실제로 차단 안 됐던 API)으로 같은
    시군구를 검색해서 우리 DB에 없는 단지가 있는지 대조한다. 실제로
    이 방식으로 사용자와 함께 검증하다가 분양중 아파트(B01) 필터링
    누락을 실제로 찾아냄(양평군 82건 중 진짜 누락 2건, 나머지 5건은
    "(주상복합)"/"(도시형)" 같은 접미사 차이로 인한 오탐 -- 비교 시
    `_normalize_complex_name`(괄호+"아파트"/"주상복합" 등 제거)으로
    걸러짐). 등록/생성은 하지 않고 "확인 필요" 후보만 만든다(관리자가
    직접 판단해서 단지 추가 화면으로 등록 -- 새 단지를 검증 없이
    자동으로 막 만들지 않기 위함, CLAUDE.md 4번 원칙과 3번 원칙의
    균형점)."""
    job_id = job["id"]
    bare_sigungu = _bare_sigungu(job["sigungu_query"])

    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT name FROM apartment_complexes WHERE sigungu = :sigungu"),
            {"sigungu": bare_sigungu},
        ).scalars().all()
    our_names = {_normalize_complex_name(name) for name in rows}

    client = NaverComplexClient()
    seen_numbers: set[int] = set()
    all_items: list[dict[str, Any]] = []
    page = 0
    consecutive_failures = 0
    while True:
        if _job_cancelled(job_id):
            _finish_job(job_id, status="cancelled")
            return
        try:
            result = _call_with_retry(client.search_by_keyword, bare_sigungu, page=page)
            consecutive_failures = 0
        except NaverComplexLookupError as exc:
            consecutive_failures += 1
            logger.warning(
                "이중검사 검색 실패: job_id=%s page=%s error=%s", job_id, page, exc,
            )
            if consecutive_failures >= 5:
                _finish_job(
                    job_id,
                    status="failed",
                    error_message=f"네이버 검색이 반복 실패했습니다: {exc}",
                )
                return
            _polite_sleep(page)
            continue

        for item in result.get("list") or []:
            number = item.get("complexNumber")
            if number is None or number in seen_numbers:
                continue
            seen_numbers.add(number)
            all_items.append(item)

        total_count = result.get("totalCount") or len(all_items)
        # total_dong_count/processed_dong_count는 sweep 전용 이름이지만
        # 이 job_kind에서는 "네이버가 알려준 총 건수/지금까지 받은 건수"로
        # 재해석해서 관리자 화면 진행률 표시를 그대로 재사용한다(새 컬럼
        # 안 만듦).
        with SessionLocal() as session:
            repository.update_job(
                session,
                job_id=job_id,
                changes={
                    "total_dong_count": total_count,
                    "processed_dong_count": len(all_items),
                },
            )
            session.commit()

        if not result.get("hasNextPage"):
            break
        page += 1
        _polite_sleep(page)

    missing = []
    for item in all_items:
        normalized = _normalize_complex_name(item.get("complexName"))
        if normalized and normalized not in our_names:
            missing.append({
                "naver_complex_number": item.get("complexNumber"),
                "name": item.get("complexName"),
                "type_code": item.get("type"),
                "eupmyeondong": item.get("legalDivisionName"),
            })

    with SessionLocal() as session:
        repository.update_job(
            session,
            job_id=job_id,
            changes={
                "total_count": len(all_items),
                "success_count": len(all_items) - len(missing),
                "failed_count": len(missing),
                "summary": {
                    "cross_check_naver_total": len(all_items),
                    "cross_check_our_total": len(our_names),
                    "cross_check_missing": missing,
                },
            },
        )
        session.commit()
    _finish_job(job_id, status="completed_with_errors" if missing else "completed")


def _worker_loop() -> None:
    while True:
        try:
            with SessionLocal() as session:
                with session.begin():
                    job = repository.next_runnable_job(session)
            if job:
                try:
                    _run_job(job)
                except Exception as exc:
                    logger.exception(
                        "시군구 단지 자동수집 작업 중단", extra={"job_id": job["id"]}
                    )
                    _finish_job(job["id"], status="failed", error_message=str(exc)[:2000])
            else:
                time.sleep(3)
        except Exception:
            logger.exception("시군구 단지 자동수집 worker polling 오류")
            time.sleep(5)


def start_complex_region_import_worker() -> None:
    """단일 uvicorn 프로세스에서 한 worker만 시작하고 재기동 시 running
    작업을 잇는다(bulk_import.worker.start_bulk_import_worker와 동일한
    패턴)."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop,
            name="zipterior-complex-region-import",
            daemon=True,
        )
        thread.start()
        _worker_started = True
