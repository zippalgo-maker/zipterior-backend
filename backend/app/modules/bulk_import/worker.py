import json
import logging
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.admin.complex_service import (
    AdminComplexDuplicateError,
    AdminComplexService,
)
from app.modules.admin.kakao_complex_client import (
    KakaoComplexLookupError,
    search_complex_by_building_name,
)
from app.modules.admin.naver_complex_client import (
    NaverComplexClient,
    NaverComplexLookupError,
)
from app.modules.bulk_import import repository
from app.modules.bulk_import.excel_portfolio import load_portfolio_workbook
from app.modules.bulk_import.mapping import (
    apply_confidence_text,
    build_confidence,
    build_image_captions,
    content_blocks_from_item,
    content_blocks_overview,
    grouped_portfolio_spaces,
    portfolio_overview,
    portfolio_overview_from_confidence,
    portfolio_summary,
    representative_image_index,
    select_portfolio_images,
    source_space_key,
)
from app.modules.notifications.service import NotificationService
from app.modules.portfolios.constants import classify_construction_scope
from app.modules.portfolios.image_service import (
    MAX_IMAGES_PER_PORTFOLIO,
    save_admin_imported_image,
)
from app.modules.portfolios.repository import (
    count_portfolio_images as count_existing_portfolio_images,
)


logger = logging.getLogger(__name__)
ALLOWED_IMAGE_HOSTS = {
    "prs.ohouse.com",
    "prs.ohou.se",
    "bucketplace-v2-development.s3.amazonaws.com",
}
MAX_REMOTE_IMAGE_SIZE = 25 * 1024 * 1024
# 원본 이미지는 오늘의집 CDN(ALLOWED_IMAGE_HOSTS) 세 호스트에서만 받아온다.
# 순차 다운로드는 포트폴리오당 이미지가 많을 때(수십 장) 매우 느리지만,
# 동시 연결 수를 너무 올리면 상대 서버에 부하를 주거나 차단(rate limit)될
# 위험이 있다. 포트폴리오 하나 안에서만 이 숫자만큼 동시에 받고(작업 전체는
# 여전히 포트폴리오 단위로 순차 처리하므로 이 값이 곧 소스 서버에 대한
# 전체 시스템의 최대 동시 연결 수다), 값을 올리기 전에 실제 실패율이
# 늘어나는지 반드시 확인한다.
IMAGE_DOWNLOAD_CONCURRENCY = 4
_worker_lock = threading.Lock()
_worker_started = False


def _text(value: Any, limit: int) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized[:limit] or None


def _is_public_address(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for address in addresses:
        ip = address[4][0]
        if ip.startswith(("10.", "127.", "169.254.", "192.168.")):
            return False
        if ip.startswith("172."):
            second = int(ip.split(".")[1])
            if 16 <= second <= 31:
                return False
        if ip in {"::1", "0.0.0.0"} or ip.lower().startswith(("fc", "fd", "fe80")):
            return False
    return True


def _download_image(url: str) -> tuple[bytes, str, str]:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_IMAGE_HOSTS:
        raise ValueError("허용되지 않은 이미지 URL입니다.")
    if not _is_public_address(host):
        raise ValueError("이미지 호스트를 안전하게 확인할 수 없습니다.")
    request = Request(
        url,
        headers={
            "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.5",
            "User-Agent": "ZipteriorBulkImporter/2.4 (+https://zipterior.kr)",
        },
    )
    with urlopen(request, timeout=20) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or (final.hostname or "").lower() not in ALLOWED_IMAGE_HOSTS:
            raise ValueError("이미지 요청이 허용되지 않은 주소로 이동했습니다.")
        content_type = str(response.headers.get_content_type() or "").lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
            raise ValueError("JPG, PNG, WEBP, AVIF 이미지가 아닙니다.")
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > MAX_REMOTE_IMAGE_SIZE:
            raise ValueError("원격 이미지가 25MB를 초과합니다.")
        data = response.read(MAX_REMOTE_IMAGE_SIZE + 1)
    if not data or len(data) > MAX_REMOTE_IMAGE_SIZE:
        raise ValueError("원격 이미지 크기를 확인할 수 없거나 25MB를 초과합니다.")
    filename = Path(final.path).name or "imported-image"
    if content_type == "image/avif":
        # 오늘의집 CDN은 URL 확장자가 JPG/PNG여도 Accept 협상에 따라 AVIF를
        # 반환한다. 기존 포트폴리오 이미지 파이프라인이 검증 가능한 WEBP로
        # 한 번 변환해 저장하며, AVIF 원본을 형식 오류로 버리던 방식을 대체한다.
        # v2.5.1 일괄등록 속도저하(job #29/#30) 원인 분석 결과 -- 2026-08-21
        # (V2.5.0_PLAN.md 참고): method=6(libwebp 최고 압축 노력, 가장 느림)이
        # image_service.py의 _save_webp_variant()에서 2026-08-19에 이미
        # method=4로 낮춰 인코딩 시간을 절반으로 줄인 것과 동일한 문제였는데
        # 여기(AVIF 원본 변환 경로)만 그 최적화가 빠져 있었다. quality=92는
        # 최종 배포용 변형이 아니라 표준 파이프라인에 넘기기 전 원본 화질
        # 보존이 목적이라 그대로 두고, 속도만 문제였던 method만 낮춘다.
        avif_started = time.perf_counter()
        try:
            with Image.open(BytesIO(data)) as source:
                if str(source.format or "").upper() != "AVIF":
                    raise ValueError("AVIF 본문 형식이 응답 헤더와 다릅니다.")
                source.load()
                converted = source.copy()
            if converted.mode not in {"RGB", "RGBA"}:
                converted = converted.convert("RGB")
            output = BytesIO()
            converted.save(output, format="WEBP", quality=92, method=4)
            data = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("AVIF 이미지를 안전하게 변환하지 못했습니다.") from exc
        finally:
            avif_elapsed_ms = round((time.perf_counter() - avif_started) * 1000, 1)
            logger.info(
                "AVIF->WEBP 변환 소요시간: url=%s duration_ms=%s",
                url, avif_elapsed_ms,
            )
        if not data or len(data) > MAX_REMOTE_IMAGE_SIZE:
            raise ValueError("변환된 이미지가 비어 있거나 25MB를 초과합니다.")
        content_type = "image/webp"
        filename = f"{Path(filename).stem}.webp"
    return data, content_type, filename[:255]


def _job_cancelled(job_id: int) -> bool:
    with SessionLocal() as session:
        job = repository.find_job(session, job_id=job_id)
        return job is None or job["status"] == "cancelled"


def _sync_job_counts(job_id: int) -> None:
    with SessionLocal() as session:
        counts = repository.record_status_counts(session, job_id=job_id)
        repository.update_job(
            session,
            job_id=job_id,
            changes={
                "processed_count": sum(
                    counts.get(value, 0)
                    for value in ("succeeded", "duplicate", "failed", "skipped")
                ),
                "success_count": counts.get("succeeded", 0),
                "duplicate_count": counts.get("duplicate", 0),
                "failed_count": counts.get("failed", 0),
            },
        )
        session.commit()


def _finish_job(job_id: int, *, summary_updates: dict[str, Any] | None = None) -> None:
    with SessionLocal() as session:
        job = repository.find_job(session, job_id=job_id)
        if job is None or job["status"] == "cancelled":
            return
        counts = repository.record_status_counts(session, job_id=job_id)
        failed = counts.get("failed", 0)
        skipped = max(int(job.get("skipped_count") or 0), counts.get("skipped", 0))
        duplicate = counts.get("duplicate", 0)
        status = (
            "completed_with_errors"
            if failed or int(job.get("image_failed_count") or 0)
            else "completed"
        )
        summary = dict(job.get("summary") or {})
        summary.update(summary_updates or {})
        repository.update_job(
            session,
            job_id=job_id,
            changes={
                "status": status,
                "summary": summary,
                "processed_count": sum(
                    counts.get(value, 0)
                    for value in ("succeeded", "duplicate", "failed", "skipped")
                ),
                "success_count": counts.get("succeeded", 0),
                "duplicate_count": duplicate,
                "failed_count": failed,
                "skipped_count": skipped,
            },
        )
        session.execute(
            text("UPDATE bulk_import_jobs SET completed_at=NOW() WHERE id=:job_id"),
            {"job_id": job_id},
        )
        session.commit()


def _process_complex_job(job: dict[str, Any]) -> None:
    job_id = int(job["id"])
    naver_failures: list[str] = []
    while not _job_cancelled(job_id):
        with SessionLocal() as session:
            records = repository.list_records(
                session, job_id=job_id, status="resolved", limit=1, offset=0
            )
            if not records:
                break
            record = records[0]
            repository.update_record(
                session, record_id=record["id"], changes={"status": "processing"}
            )
            session.commit()
        payload = dict(record["payload"])
        naver_data: dict[str, Any] | None = None
        try:
            naver_data = NaverComplexClient().lookup(
                name=payload["name"],
                latitude=payload["latitude"],
                longitude=payload["longitude"],
            )
        except NaverComplexLookupError:
            naver_failures.append(payload["name"])
        values = {
            "name": payload["name"],
            "sido": payload.get("sido"),
            "sigungu": payload.get("sigungu"),
            "eupmyeondong": payload.get("eupmyeondong"),
            "road_address": payload.get("road_address"),
            "jibun_address": payload.get("jibun_address"),
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
            "completion_year": None,
            "household_count": None,
            "building_count": None,
            "parking_count": None,
            "heating_type": None,
            "builder_name": None,
        }
        if naver_data:
            for key in (
                "completion_year", "household_count", "building_count",
                "parking_count", "heating_type", "builder_name",
            ):
                values[key] = naver_data.get(key)
        try:
            with SessionLocal() as session:
                types = list((naver_data or {}).get("apartment_types") or [])
                if types:
                    # 네이버에서는 평면도 이미지를 수집하지 않고 기본형/확장형 여부만
                    # 가져온다. 저장 계층의 명시적 nullable 계약에 맞춰 경로를 None으로
                    # 전달한다 (_ensure_portfolio_complex와 동일한 처리).
                    types = [
                        {**type_values, "floor_plan_path": None}
                        for type_values in types
                    ]
                    result = AdminComplexService.create_complex_with_types(
                        session,
                        admin_user_id=job["requested_by"],
                        values=values,
                        apartment_types=types,
                    )
                else:
                    result = AdminComplexService.create_complex(
                        session,
                        admin_user_id=job["requested_by"],
                        values=values,
                    )
                repository.update_record(
                    session,
                    record_id=record["id"],
                    changes={
                        "status": "succeeded",
                        "target_id": result["id"],
                        "result": {"naver_collected": bool(naver_data), "type_count": len(types)},
                        "error_message": None,
                    },
                )
                session.commit()
        except AdminComplexDuplicateError as exc:
            with SessionLocal() as session:
                repository.update_record(
                    session,
                    record_id=record["id"],
                    changes={"status": "duplicate", "error_message": str(exc)},
                )
                session.commit()
        except Exception as exc:
            logger.exception("단지 일괄등록 행 처리 실패", extra={"job_id": job_id})
            with SessionLocal() as session:
                repository.update_record(
                    session,
                    record_id=record["id"],
                    changes={"status": "failed", "error_message": str(exc)[:2000]},
                )
                session.commit()
        _sync_job_counts(job_id)
    if naver_failures:
        unique_names = list(dict.fromkeys(naver_failures))
        shown = unique_names[:100]
        suffix = f" 외 {len(unique_names)-len(shown)}개" if len(unique_names) > len(shown) else ""
        message = "네이버 정보를 불러오지 못해 주소 기본정보만 등록한 단지: " + ", ".join(shown) + suffix
        with SessionLocal() as session:
            NotificationService.create(
                session,
                user_id=job["requested_by"],
                notification_type="bulk_complex_naver_failed",
                title=f"단지 일괄등록 네이버 확인 실패 {len(unique_names)}건",
                message=message,
                target_type="bulk_import_job",
                target_id=job_id,
            )
            session.commit()
        _finish_job(job_id, summary_updates={"naver_failed_names": unique_names})
    else:
        _finish_job(job_id, summary_updates={"naver_failed_names": []})


def _company_source_key(portfolio: dict[str, Any]) -> str:
    return str(portfolio.get("writer_id") or portfolio.get("expert_id") or "").strip()


def _company_values(source: dict[str, Any], portfolio: dict[str, Any]) -> dict[str, Any]:
    nested = portfolio.get("company") if isinstance(portfolio.get("company"), dict) else {}
    name = (
        _text(source.get("company_name"), 200)
        or _text(portfolio.get("company_name"), 200)
        or _text(nested.get("name"), 200)
        or _text(portfolio.get("writer_nickname"), 200)
        or f"전문가 {portfolio.get('writer_id') or portfolio.get('portfolio_id')}"
    )
    return {
        "name": name,
        "business_number": _text(source.get("business_registration_number"), 100),
        "representative_name": _text(source.get("representative_name"), 100),
        "phone": _text(source.get("phone"), 30),
        "email": _text(source.get("email"), 320),
        "address": _text(source.get("address"), 1000),
        "intro": _text(portfolio.get("writer_introduction"), 10000),
        "website_url": _text(
            source.get("website")
            or source.get("expert_url")
            or portfolio.get("expert_url"),
            2000,
        ),
    }


def _ensure_company(
    session,
    *,
    job: dict[str, Any],
    portfolio: dict[str, Any],
    company_sources: dict[str, dict[str, Any]],
) -> int:
    source_key = _company_source_key(portfolio)
    if not source_key:
        source_key = f"portfolio-writer-{portfolio.get('portfolio_id')}"
    linked = repository.source_target(
        session, source_system="ohou", entity_type="company", source_key=source_key
    )
    if linked:
        return linked
    source = company_sources.get(source_key, {})
    values = _company_values(source, portfolio)
    # 원본 writer 링크가 없는 기존 업체와 연결할 때는 사업자번호 또는
    # 이름+주소가 모두 일치하는 경우만 같은 업체로 본다. 주소가 비어 있는
    # 동명이인을 이름만으로 합치던 구형 방식은 업체 데이터 오염 위험이 있다.
    company_id = repository.find_company_for_import(
        session,
        name=values["name"],
        address=values.get("address"),
        business_number=values.get("business_number"),
    )
    if company_id is None:
        company_id = repository.create_import_company(
            session,
            admin_user_id=job["requested_by"],
            source_key=source_key,
            values=values,
            publish_immediately=bool(job["options"].get("publish_immediately", True)),
        )
    repository.create_source_link(
        session,
        source_system="ohou",
        entity_type="company",
        source_key=source_key,
        target_id=company_id,
        metadata={
            "is_confirmed": bool(source.get("is_confirmed")),
            "match_status": source.get("expert_match_status"),
        },
    )
    return company_id


def _budget_won(value: Any) -> int | None:
    try:
        amount = int(float(value or 0))
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return amount if amount >= 100_000 else amount * 10_000


def _construction_days(value: Any) -> int | None:
    try:
        months = int(float(value or 0))
    except (TypeError, ValueError):
        return None
    return months * 30 if 1 <= months <= 120 else None


def _parsed_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    raw = str(value or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


_APARTMENT_NAME_DONG_HO_SUFFIX_RE = re.compile(r"@\s*[0-9A-Za-z]+\s*-\s*[0-9]+\s*호\s*$")


def _normalize_apartment_name(raw: Any) -> str | None:
    """v5.3 크롤러의 apartment_name에는 간혹 동·호수가 "이름@동-호호"
    형태로 붙어 있다(예: "하안동 하안주공1단지@110-1012호", 실제 v5.3
    파일에서 3건 확인, 2026-08-22). 이걸 그대로 카카오/네이버 검색이나
    기존 단지 이름 매칭에 쓰면 꼬리 문자열 때문에 못 찾을 수 있어서
    검색용으로 쓰기 전에 떼어낸다. 동/호 자체는 이 함수가 버리는 게
    아니라 별도 `dong`/`ho` 컬럼(대부분 이 경우 크롤러가 이미
    채워둠)으로 남아있다."""
    text_value = str(raw or "").strip()
    if not text_value:
        return None
    return _APARTMENT_NAME_DONG_HO_SUFFIX_RE.sub("", text_value).strip() or None


def _ensure_portfolio_complex(
    *,
    job: dict[str, Any],
    item: dict[str, Any],
    resolution: dict[str, Any],
) -> tuple[int | None, bool, bool | None]:
    """JSON 주소로 기존 단지를 찾고, 없을 때만 기본정보와 타입을 생성한다."""
    # 실측 확인(job#33, 2026-08-22): street_address가 없는 포트폴리오는
    # 미리보기 단계(`_preview_company_portfolio_data`)가 payload["name"]에
    # apartment_name 원본을 그대로(정규화 없이) 저장해 두고, 그 값이
    # `resolve_complexes`를 거치지 않은 채(주소가 없어 카카오 지오코딩
    # 대상 자체가 아니었으므로) 그대로 여기까지 내려온다. 예전 코드는
    # `resolution.get("name") or _normalize_apartment_name(...)` 순서라
    # resolution.get("name")이 이미 값이 있으면(비어있지 않은 원본
    # 문자열이면) 뒤의 정규화가 아예 실행되지 않아 "@110-1012호" 꼬리가
    # 그대로 카카오 검색어에 들어가는 버그였다(실제 job#33 로그로 확인:
    # "하안동 하안주공1단지@110-1012호" 그대로 검색해 실패). 두 후보를
    # 합친 뒤 마지막에 한 번만 정규화해서 어느 쪽이 선택되든 항상 적용되게
    # 고침.
    name = _text(
        _normalize_apartment_name(resolution.get("name") or item.get("apartment_name")),
        200,
    )
    road_address = _text(
        resolution.get("road_address") or item.get("street_address"),
        500,
    )
    with SessionLocal() as session:
        existing = repository.find_complex_for_import(
            session,
            name=name,
            road_address=road_address,
            sigungu=resolution.get("sigungu"),
        )
    if existing:
        return int(existing["id"]), False, None

    latitude = resolution.get("latitude")
    longitude = resolution.get("longitude")
    if not road_address or latitude is None or longitude is None:
        # v2.5.1: 주소가 없어도 건물명(또는 크롤러가 v4에서 새로 넣은
        # address_lookup_query -- apartment_name이 비어있어도 검색 가능한
        # 텍스트가 남아있는 경우가 많다)이 있으면, 관리자 화면을 거치지
        # 않고 서버가 스스로 카카오에서 단지를 찾아본다(CLAUDE.md 4번
        # 원칙 -- "서버가 스스로" 처리를 우선). 건물명 실패 시에만
        # address_lookup_query로 한 번 더 시도(순서 중요 -- 건물명이 더
        # 신뢰도 높은 신호). 둘 다 실패/애매하면 조용히 넘어가 아래 기존
        # 조건에서 걸러져 review_reason='address_missing'으로 남는다
        # (기존 확인필요 규칙 그대로 유지, 요청사항).
        candidates = list(dict.fromkeys(filter(None, (
            name,
            _text(_normalize_apartment_name(item.get("address_lookup_query")), 300),
        ))))
        kakao_result = None
        # v2.5.1 일괄등록 속도저하(job #29) 원인 확인용 실측 로깅 -- 2026-08-21.
        # 포트폴리오 1건당 카카오 검색(후보 최대 2개, 각각 최대 2회 호출)에
        # 실제로 얼마나 걸리는지 총합을 남긴다(가설 검증용, V2.5.0_PLAN.md 참고).
        kakao_started = time.perf_counter()
        for candidate in candidates:
            try:
                kakao_result = search_complex_by_building_name(candidate)
            except KakaoComplexLookupError:
                logger.warning(
                    "건물명 기반 단지 검색 실패",
                    exc_info=True,
                    extra={"job_id": job.get("id"), "building_name": candidate},
                )
                kakao_result = None
            if kakao_result:
                break
        kakao_elapsed_ms = round((time.perf_counter() - kakao_started) * 1000, 1)
        logger.info(
            "포트폴리오 건물명 매칭 카카오 검색 총 소요시간: job_id=%s "
            "candidates=%s found=%s duration_ms=%s",
            job.get("id"), candidates, bool(kakao_result), kakao_elapsed_ms,
        )
        if kakao_result:
            # 카카오가 찾은 정식 명칭이 있으면 검색에 쓴 원본 문자열보다
            # 그걸 최종 단지 이름으로 쓴다(kakao_complex_client 설명 참고).
            name = _text(kakao_result["name"], 200) or name
            road_address = kakao_result["road_address"]
            latitude = kakao_result["latitude"]
            longitude = kakao_result["longitude"]
            resolution = {**resolution, **kakao_result}
            with SessionLocal() as session:
                existing = repository.find_complex_for_import(
                    session, name=name, road_address=road_address,
                    sigungu=kakao_result.get("sigungu"),
                )
            if existing:
                return int(existing["id"]), False, None
    if not name or not road_address or latitude is None or longitude is None:
        return None, False, None

    naver_data: dict[str, Any] | None = None
    # 확정된 네이버 표기가 '경남'처럼 짧으면 자동완성 상위 결과에서 실제 단지가
    # 빠질 수 있다. 확정명 조회 실패 때 원본의 동 포함 이름으로 한 번 더 조회해
    # 주소·좌표가 맞는 후보를 찾고, 두 방식이 모두 실패한 경우만 알림 대상으로 둔다.
    lookup_names = list(dict.fromkeys(filter(None, (
        name,
        _text(item.get("apartment_name"), 200),
    ))))
    for lookup_name in lookup_names:
        try:
            naver_data = NaverComplexClient().lookup(
                name=lookup_name,
                latitude=float(latitude),
                longitude=float(longitude),
            )
            break
        except NaverComplexLookupError:
            # 네이버 보강 실패는 주소 단지 등록 자체를 막지 않는다. 작업 결과와
            # 관리자 알림에서 따로 확인할 수 있도록 모든 후보 실패 시 False를 반환한다.
            continue

    values = {
        "name": name,
        "sido": resolution.get("sido"),
        "sigungu": resolution.get("sigungu"),
        "eupmyeondong": resolution.get("eupmyeondong"),
        "road_address": road_address,
        "jibun_address": resolution.get("jibun_address"),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "completion_year": None,
        "household_count": None,
        "building_count": None,
        "parking_count": None,
        "heating_type": None,
        "builder_name": None,
    }
    if naver_data:
        for key in (
            "completion_year",
            "household_count",
            "building_count",
            "parking_count",
            "heating_type",
            "builder_name",
        ):
            values[key] = naver_data.get(key)

    try:
        with SessionLocal() as session:
            apartment_types = list(
                (naver_data or {}).get("apartment_types") or []
            )
            if apartment_types:
                # 네이버에서는 평면도 이미지를 수집하지 않고 기본형/확장형 여부만
                # 가져온다. 저장 계층의 명시적 nullable 계약에 맞춰 경로를 None으로
                # 전달하며, 과거의 누락된 바인드값 호출 방식을 대체한다.
                apartment_types = [
                    {**type_values, "floor_plan_path": None}
                    for type_values in apartment_types
                ]
                result = AdminComplexService.create_complex_with_types(
                    session,
                    admin_user_id=job["requested_by"],
                    values=values,
                    apartment_types=apartment_types,
                )
            else:
                result = AdminComplexService.create_complex(
                    session,
                    admin_user_id=job["requested_by"],
                    values=values,
                )
        return int(result["id"]), True, bool(naver_data)
    except AdminComplexDuplicateError:
        # 동시에 같은 단지가 생성된 경우 새 중복을 만들지 않고 방금 생성된
        # 정상 단지를 다시 찾아 포트폴리오 연결 대상으로 사용한다.
        with SessionLocal() as session:
            existing = repository.find_complex_for_import(
                session,
                name=name,
                road_address=road_address,
                sigungu=values.get("sigungu"),
            )
        if existing:
            return int(existing["id"]), False, bool(naver_data)
        raise


def _import_one_image(
    *,
    job: dict[str, Any],
    job_id: int,
    source_key: str,
    company_id: int,
    portfolio_id: int,
    space_ids: dict[str, int],
    room_codes: dict[str, str],
    image_captions_by_order: dict[int, str],
    image: dict[str, Any],
    image_index: int,
    sort_order: int,
    is_representative: bool,
    bypass_editable_status: bool = False,
) -> str:
    """이미지 한 장을 내려받고 리사이즈·인코딩·DB저장까지 전부 한 번에
    한다. 스레드 풀에서 같은 포트폴리오의 여러 이미지가 동시에 이 함수를
    실행하므로:
    - 다운로드/PIL 리사이즈/WebP 인코딩은 원래도 스레드 세이프한 순수
      로컬 작업이라 문제없다.
    - sort_order/is_representative는 호출한 쪽(_process_json_portfolio)이
      배치 전체를 보고 미리 계산해서 넘겨준 값을 그대로 쓴다 -- 이 함수
      안에서 "현재 DB 상태"를 읽어서 판단하면 동시 실행 시 여러 이미지가
      같은 sort_order를 받거나 대표사진이 중복 지정될 수 있기 때문
      (save_admin_imported_image의 override 파라미터로 그 내부 계산을
      건너뛴다).
    - DB 세션은 함수 안에서 새로 열고 닫아 스레드끼리 공유하지 않는다.
    반환값은 'success' | 'failed'."""
    try:
        data, content_type, filename = _download_image(str(image.get("image_url") or ""))
        source_group = source_space_key(image)
        target_space_id = space_ids.get(source_group)
        if target_space_id is None:
            raise ValueError("원본 이미지의 공간을 포트폴리오 공간과 연결할 수 없습니다.")
        room_code = room_codes[source_group]
        image_caption = image_captions_by_order.get(image.get("document_order"))
        image_key = f"{source_key}:{image.get('image_order') or image_index}"
        with SessionLocal() as session:
            saved = save_admin_imported_image(
                session,
                admin_user_id=job["requested_by"],
                company_id=company_id,
                portfolio_id=portfolio_id,
                room_code=room_code,
                portfolio_space_id=target_space_id,
                original_filename=filename,
                content_type=content_type,
                file_data=data,
                description=image_caption,
                sort_order_override=sort_order,
                is_representative_override=is_representative,
                bypass_editable_status=bypass_editable_status,
            )
            repository.create_source_link(
                session,
                source_system="ohou",
                entity_type="portfolio_image",
                source_key=image_key,
                target_id=saved["id"],
                metadata={
                    "portfolio_source_key": source_key,
                    "image_url": image.get("image_url"),
                    "source_group": source_group,
                    "phase": image.get("phase"),
                },
            )
            session.commit()
        return "success"
    except Exception:
        logger.warning(
            "포트폴리오 원격 이미지 등록 실패",
            exc_info=True,
            extra={"job_id": job_id, "portfolio_id": source_key},
        )
        return "failed"


def _include_content_block_only_images(
    *,
    item: dict[str, Any],
    content_blocks: list[dict[str, Any]],
    selected_images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """v2.5.1: select_portfolio_images는 phase=="AFTER"인 사진만 고른다
    (방별 갤러리는 원래 시공 후 사진만 의미가 있어서). 그런데 content_blocks
    (원문 재현)에는 작성자가 넣은 BEFORE(시공 전) 비교 사진도 그대로 나온다
    -- 실측 결과 원본에서 이렇게 빠지는 사진의 100%가 BEFORE phase였다
    (1,031장/전체 실측). 그 사진들도 안 받으면 본문에는 나오는데 우리
    서버엔 없는 사진이 남는다("모든 데이터는 우리 서버에" 원칙 위반).
    대표사진·공간배정 계산(representative_image_index)은 이 함수를 호출하기
    전의 selected_images로 이미 끝났어야 한다 -- 그 계산에는 영향을 안 준다.
    `_process_json_portfolio`와 백필 스크립트가 이 함수를 공유한다."""
    if not content_blocks:
        return selected_images
    selected_urls = {image.get("image_url") for image in selected_images}
    content_block_image_urls = {
        block.get("image_url")
        for block in content_blocks
        if block.get("node_type") == "image"
    }
    missing_urls = content_block_image_urls - selected_urls
    if not missing_urls:
        return selected_images
    all_images_by_url = {
        image.get("image_url"): image for image in (item.get("images") or [])
    }
    return selected_images + [
        all_images_by_url[url] for url in missing_urls if url in all_images_by_url
    ]


def _download_selected_images(
    *,
    job: dict[str, Any],
    job_id: int,
    source_key: str,
    company_id: int,
    portfolio_id: int,
    space_ids: dict[str, int],
    room_codes: dict[str, str],
    image_captions_by_order: dict[int, str],
    selected_images: list[dict[str, Any]],
    representative_index: int,
    bypass_editable_status: bool = False,
) -> tuple[int, int]:
    """v2.5.1: `selected_images` 중 아직 우리 서버에 없는 것만 내려받아
    저장한다(이미 있는 건 source_import_links로 걸러 재다운로드 안 함).
    `_process_json_portfolio`의 정상 흐름과 백필 스크립트
    (scripts/backfill_content_blocks_images.py)가 이 함수를 공유한다.
    bypass_editable_status는 백필처럼 이미 승인·공개된 포트폴리오에도
    사진을 추가해야 할 때만 백필 스크립트가 True로 넘긴다(정상 대량등록
    흐름은 기본값 False 그대로 -- save_admin_imported_image 설명 참고).
    (image_success, image_failed) 카운트를 돌려준다."""
    with SessionLocal() as session:
        existing_count = count_existing_portfolio_images(session, portfolio_id=portfolio_id)
    to_fetch: list[tuple[int, dict[str, Any]]] = []
    for image_index, image in enumerate(selected_images, start=1):
        image_key = f"{source_key}:{image.get('image_order') or image_index}"
        with SessionLocal() as session:
            existing_image_id = repository.source_target(
                session,
                source_system="ohou",
                entity_type="portfolio_image",
                source_key=image_key,
            )
        if not existing_image_id:
            to_fetch.append((image_index, image))
    image_failed = 0
    room_left = max(0, MAX_IMAGES_PER_PORTFOLIO - existing_count)
    if len(to_fetch) > room_left:
        image_failed += len(to_fetch) - room_left
        to_fetch = to_fetch[:room_left]

    image_success = 0
    if to_fetch:
        with ThreadPoolExecutor(max_workers=IMAGE_DOWNLOAD_CONCURRENCY) as pool:
            outcomes = pool.map(
                lambda enumerated: _import_one_image(
                    job=job,
                    job_id=job_id,
                    source_key=source_key,
                    company_id=company_id,
                    portfolio_id=portfolio_id,
                    space_ids=space_ids,
                    room_codes=room_codes,
                    image_captions_by_order=image_captions_by_order,
                    image=enumerated[1][1],
                    image_index=enumerated[1][0],
                    sort_order=existing_count + enumerated[0],
                    is_representative=(
                        existing_count == 0
                        and enumerated[1][0] == representative_index + 1
                    ),
                    bypass_editable_status=bypass_editable_status,
                ),
                enumerate(to_fetch),
            )
            for outcome in outcomes:
                if outcome == "success":
                    image_success += 1
                else:
                    image_failed += 1
    return image_success, image_failed


def _localize_and_save_content_blocks(
    *,
    job_id: int,
    portfolio_id: int,
    source_key: str,
    content_blocks: list[dict[str, Any]],
    content_blocks_stats: dict[str, int],
) -> dict[str, int]:
    """v2.5.1: content_blocks(원문 재현)의 image_url을 원본(외부 CDN) 대신
    우리 서버 경로로 바꿔서 저장한다 -- 반드시 이미지가 다운로드된 뒤에
    호출할 것(그래야 매핑을 찾을 수 있다). `_process_json_portfolio`와
    백필 스크립트가 이 함수를 공유한다. 별도 세션·별도 트랜잭션이라 여기서
    문제가 생겨도 본 등록(포트폴리오·공간·이미지)에는 영향이 없다."""
    if not content_blocks:
        return content_blocks_stats
    with SessionLocal() as lookup_session:
        local_urls = repository.local_image_urls_for_source(
            lookup_session, portfolio_source_key=source_key
        )
    localized_count = 0
    for block in content_blocks:
        original_url = block.get("image_url")
        if not original_url or original_url not in local_urls:
            continue
        local_path = local_urls[original_url]
        block["image_url"] = local_path
        # raw_node.imageUrl도 같이 맞춰 둔다 -- 프론트는 block.image_url을
        # 우선 쓰지만(외부 URL이 안 남게 하는 게 원칙이라 둘 다 맞춘다),
        # raw_node를 직접 참조하는 코드가 나중에 생겨도 어긋나지 않게.
        if isinstance(block.get("raw_node"), dict) and block["raw_node"].get(
            "imageUrl"
        ):
            block["raw_node"]["imageUrl"] = local_path
        localized_count += 1
    content_blocks_stats["images_localized_count"] = localized_count
    content_blocks_stats["images_still_external_count"] = (
        sum(1 for b in content_blocks if b.get("node_type") == "image")
        - localized_count
    )
    try:
        with SessionLocal() as cb_session:
            repository.replace_content_blocks(
                cb_session, portfolio_id=portfolio_id, blocks=content_blocks
            )
            cb_session.commit()
    except Exception:
        logger.warning(
            "content_blocks 저장 실패(테스트 기능, 본 등록에는 영향 없음)",
            exc_info=True,
            extra={"job_id": job_id, "portfolio_id": portfolio_id},
        )
    return content_blocks_stats


def _process_json_portfolio(
    job: dict[str, Any],
    item: dict[str, Any],
    company_sources: dict[str, dict[str, Any]],
) -> None:
    job_id = int(job["id"])
    source_key = str(item.get("portfolio_id") or "").strip()
    if not source_key:
        raise ValueError("portfolio_id가 없습니다.")
    space_groups = grouped_portfolio_spaces(item)
    room_codes = {space["key"]: space["space_code"] for space in space_groups}
    confidence = build_confidence(item)
    captions = build_image_captions(item)
    room_openings, image_captions_by_order = captions if captions else (None, {})
    if confidence is not None:
        apply_confidence_text(space_groups, confidence, room_openings)
    threshold = int(job["options"].get("confidence_threshold", 80))
    confidence_ok = confidence is None or confidence.portfolio_score >= threshold
    with SessionLocal() as session:
        record_id = repository.create_record(
            session,
            job_id=job_id,
            record_type="portfolio",
            record_key=source_key,
            source_label=_text(item.get("title"), 500),
            payload={
                "portfolio_id": source_key,
                "writer_id": item.get("writer_id"),
                "image_count": len(item.get("images") or []),
            },
            status="processing",
        )
        existing_record = None
        if record_id is None:
            existing = repository.list_records(
                session, job_id=job_id, status=None, limit=10_000, offset=0
            )
            record = next(row for row in existing if row["record_key"] == source_key)
            if record["status"] in {"succeeded", "duplicate", "skipped"}:
                return
            existing_record = record
            record_id = record["id"]
            repository.update_record(
                session, record_id=record_id, changes={"status": "processing"}
            )
        resolution_payload = dict((existing_record or {}).get("payload") or {})
        linked = repository.source_target(
            session, source_system="ohou", entity_type="portfolio", source_key=source_key
        )
        if linked and (not existing_record or existing_record.get("target_id") != linked):
            repository.update_record(
                session,
                record_id=record_id,
                changes={"status": "duplicate", "target_id": linked, "error_message": "이미 가져온 포트폴리오입니다."},
            )
            session.commit()
            return
        if linked:
            portfolio = repository.find_import_portfolio(session, portfolio_id=linked)
            if portfolio is None:
                raise ValueError("이어 처리할 포트폴리오를 찾을 수 없습니다.")
            portfolio_id = linked
            company_id = portfolio["company_id"]
            complex_id = portfolio["complex_id"]
            apartment_type_id = portfolio["apartment_type_id"]
            # 이어 처리(resume) 경로 -- 이전 실행에서 이미 확정된 값을 그대로
            # 쓰므로 이번 실행에서 새로 모호함을 판정하지 않는다.
            apartment_type_ambiguous = False
            existing_spaces = repository.import_spaces(
                session,
                portfolio_id=portfolio_id,
            )
            structure_matches = len(existing_spaces) == len(space_groups) and all(
                existing["space_code"] == expected["space_code"]
                and existing["space_name"] == expected["space_name"]
                and int(existing["space_number"]) == int(expected["space_number"])
                and int(existing["sort_order"]) == int(expected["sort_order"])
                for existing, expected in zip(existing_spaces, space_groups, strict=True)
            )
            if not structure_matches:
                raise ValueError(
                    "이어 처리할 포트폴리오의 원본 공간 연결이 현재 JSON과 일치하지 않습니다."
                )
            space_ids = {
                expected["key"]: int(existing["id"])
                for existing, expected in zip(existing_spaces, space_groups, strict=True)
            }
        else:
            company_id = _ensure_company(
                session, job=job, portfolio=item, company_sources=company_sources
            )
            session.commit()
            complex_id, complex_created, complex_naver_collected = (
                _ensure_portfolio_complex(
                    job=job,
                    item=item,
                    resolution=resolution_payload,
                )
            )
            apartment_type_id = None
            apartment_type_ambiguous = False
            if complex_id:
                with SessionLocal() as lookup_session:
                    apartment_type_id, apartment_type_ambiguous = (
                        repository.resolve_type_for_import(
                            lookup_session,
                            complex_id=complex_id,
                            item=item,
                        )
                    )
            budget = _budget_won(item.get("budget"))
            # v2.5.0 (테스트, additive): content_blocks가 있으면(원본 문단
            # 데이터) 메타데이터 조합 문장보다 실제 작성자의 글을 우선한다.
            # 우선순위: confidence(paragraphs 기반, 기존) > content_blocks
            # 첫 문단(신규) > 메타데이터 템플릿(최후 fallback).
            description = (
                (confidence and portfolio_overview_from_confidence(confidence))
                or content_blocks_overview(item)
                or portfolio_overview(item)
            )
            # summary는 항상 portfolio_summary()(업체 인사말이 아닌 평형/스타일/
            # 공사범위 같은 프로젝트 사실 기반)로 만든다. description이 confidence
            # 기반(원본 글의 인사말로 시작하는 intro_text)일 때 description의
            # 첫 문단을 그대로 summary로 잘라 쓰면 그 인사말 문단이 summary와
            # description 양쪽에 그대로 중복돼 나타난다(요약이 project 사실이
            # 아니라 회사 인사말이 되어버리는 문제도 함께 있었음).
            summary = portfolio_summary(item)
            portfolio_id = repository.create_import_portfolio(
                session,
                admin_user_id=job["requested_by"],
                company_id=company_id,
                publish_immediately=bool(job["options"].get("publish_immediately", True)),
                values={
                    "complex_id": complex_id,
                    "apartment_type_id": apartment_type_id,
                    "title": _text(item.get("title"), 200) or f"포트폴리오 {source_key}",
                    "summary": summary,
                    "description": description,
                    # 2026-08-22: 크롤링 원본 텍스트를 그대로 저장하지 않고
                    # 개별등록 폼과 같은 CONSTRUCTION_SCOPE_OPTIONS로 분류해
                    # 저장한다(portfolios/constants.py 참고 -- 값 체계 불일치
                    # 수정).
                    "construction_scope": classify_construction_scope(
                        item.get("expertise")
                    ),
                    "budget_min": budget,
                    "budget_max": budget,
                    "construction_days": _construction_days(item.get("period")),
                    "construction_date": _parsed_date(item.get("created_at")),
                    "published_at": item.get("created_at"),
                },
            )
            repository.create_source_link(
                session,
                source_system="ohou",
                entity_type="portfolio",
                source_key=source_key,
                target_id=portfolio_id,
                metadata={"source_url": item.get("source_url"), "agent": item.get("agent")},
            )
            space_ids: dict[str, int] = {}
            for space in space_groups:
                space_id = repository.create_import_space(
                    session,
                    portfolio_id=portfolio_id,
                    space_code=space["space_code"],
                    space_name=space["space_name"],
                    space_number=space["space_number"],
                    description=space["description"],
                    sort_order=space["sort_order"],
                )
                space_ids[space["key"]] = space_id
            repository.update_record(
                session,
                record_id=record_id,
                changes={
                    "target_id": portfolio_id,
                    "result": {
                        "company_id": company_id,
                        "complex_id": complex_id,
                        "complex_name": resolution_payload.get("name")
                        or item.get("apartment_name"),
                        "complex_created": complex_created,
                        "complex_naver_collected": complex_naver_collected,
                        "address_resolution_error": resolution_payload.get(
                            "address_resolution_error"
                        ),
                        "confidence_score": confidence.portfolio_score if confidence else None,
                        "confidence_needs_review": confidence is not None and not confidence_ok,
                        "confidence_sections": (
                            [
                                {
                                    "label": s.label,
                                    "score": s.score,
                                    "reason": s.reason,
                                    "n_images": s.n_images,
                                    "n_text_paragraphs": s.n_text_paragraphs,
                                }
                                for s in confidence.sections
                            ]
                            if confidence
                            else None
                        ),
                        "platform_mentions_removed": (
                            confidence.platform_mentions_removed if confidence else 0
                        ),
                        "source_url": item.get("source_url"),
                    },
                },
            )
        session.commit()

    # v2.5.1: content_blocks(원문 재현) 대상 여부만 여기서 미리 계산해 둔다
    # -- 실제 저장은 아래 이미지 다운로드가 끝난 뒤로 옮겼다(원칙: "본문에
    # 나오는 사진은 전부 우리 서버에 있어야 한다" -- 외부 CDN을 그대로
    # 가리키면 원본이 지워지거나 바뀌었을 때 우리 사이트도 같이 깨진다).
    content_blocks, content_blocks_stats = content_blocks_from_item(item)

    max_images_option = job["options"].get("max_images_per_portfolio")
    max_images = int(max_images_option) if max_images_option is not None else None
    # v2.5.1: content_blocks가 있는 포트폴리오는 "포트폴리오당 이미지 상한"
    # 설정과 무관하게 원본 사진을 전부 받는다 -- 그 설정은 원래 방별 갤러리
    # (select_portfolio_images의 공간별 순환 선택) 노출 개수를 조절하려던
    # 것인데, content_blocks 본문은 그 상한을 안 보고 원본 문서에 있는
    # 사진을 전부 나열한다. 상한을 그대로 적용하면 본문에는 나오는데
    # 우리 서버엔 없는 사진이 생겨서(=외부 CDN 핫링크로 남음) 원칙에
    # 어긋난다. select_portfolio_images(max_images=None)은 이미
    # "무제한 -- 원본 순서 그대로 전부"를 지원한다(docstring 참고).
    selected_images = select_portfolio_images(
        item, max_images=(None if content_blocks else max_images)
    )
    # 대표사진: 거실 사진이 있으면 그중 첫 장, 없으면(부분 리모델링)
    # 첫 실제 공간의 첫 장 -- representative_image_index() 설명 참고.
    # (대표사진 계산은 반드시 AFTER 사진 기준 selected_images로 해야 하므로,
    # 아래에서 content_blocks용 이미지를 추가하기 전에 먼저 계산한다.)
    representative_index = representative_image_index(space_groups, selected_images)

    selected_images = _include_content_block_only_images(
        item=item, content_blocks=content_blocks, selected_images=selected_images
    )

    # v2.5.0: 원본 CDN에서 이미지를 한 장씩 순차로 받고 리사이즈·인코딩·
    # 저장까지 순차로 하던 게 병목이었다 (실측: 150건/이미지 4,349장에
    # 2시간, 장당 평균 1.7초 -- 다운로드는 0.4~0.5초뿐이라 대부분은 로컬
    # 리사이즈/WebP 인코딩/디스크 저장 시간). 이 전체를
    # IMAGE_DOWNLOAD_CONCURRENCY만큼 동시에 처리하도록 바꿨다. 포트폴리오
    # 자체는 여전히 순차 처리라 소스 서버(원본 CDN)에 대한 전체 시스템의
    # 동시 연결 수는 이 값을 넘지 않는다 -- 리사이즈·인코딩은 로컬 CPU
    # 작업이라 병렬화해도 원본 사이트에는 아무 부담을 안 준다.
    #
    # sort_order/대표사진 지정은 배치 전체를 미리 보고 계산해서 넘긴다
    # (_import_one_image 설명 참고) -- 저장 시점에 "현재 DB 상태"를 읽어
    # 판단하면 동시 저장 시 경쟁 조건이 생기기 때문.
    image_success, image_failed = _download_selected_images(
        job=job,
        job_id=job_id,
        source_key=source_key,
        company_id=company_id,
        portfolio_id=portfolio_id,
        space_ids=space_ids,
        room_codes=room_codes,
        image_captions_by_order=image_captions_by_order,
        selected_images=selected_images,
        representative_index=representative_index,
    )

    # v2.5.1: 이미지가 전부 우리 서버에 저장된 뒤에야 content_blocks를 저장한다
    # -- 저장 직전에 원본(외부 CDN) image_url을 방금 만든 우리 서버 경로로
    # 바꿔 쓴다.
    content_blocks_stats = _localize_and_save_content_blocks(
        job_id=job_id,
        portfolio_id=portfolio_id,
        source_key=source_key,
        content_blocks=content_blocks,
        content_blocks_stats=content_blocks_stats,
    )

    with SessionLocal() as session:
        # v2.5.0: 관리자가 검수 화면에서 개별 체크를 뒤집어 뒀으면(admin_selected)
        # 그 판단이 자동 신뢰도 판정(confidence_ok)보다 우선한다. 미리보기 단계를
        # 거치지 않은 레코드(admin_selected 없음)는 기존처럼 자동 판정만 따른다.
        admin_selected = resolution_payload.get("admin_selected")
        publish_ok = confidence_ok if admin_selected is None else bool(admin_selected)
        # v2.5.0: 단지(주소)나 타입(평형)을 못 찾으면 이 포트폴리오는 지도에
        # 마커를 꽂거나 평형 정보를 보여줄 수 없다. 신뢰도/체크 여부와 무관하게
        # 'draft'로 남겨서 업체가 기존 수정 화면에서 고치거나 관리자가 직접
        # 고칠 때까지 공개(승인)도, 검수대기 노출도 하지 않는다. 둘 다 없으면
        # 둘 다 채워야 공개된다 -- 사유를 쉼표로 이어붙여 동시에 남긴다
        # (관리자가 단지만 먼저 고치면 주소 사유만 지워지고 타입 사유가 남는
        # 식으로, 관리자 쪽 assign_portfolio_complex가 이 값을 다시 계산한다).
        review_reasons: list[str] = []
        if not complex_id:
            review_reasons.append(
                "address_missing"
                if not _text(item.get("street_address"), 500)
                else "complex_match_failed"
            )
        if complex_id and not apartment_type_id:
            # v5.3 우선순위 규칙(2026-08-22): 후보가 여러 개라 임의로 못 고른
            # 경우("apartment_type_ambiguous")와, 아예 어떤 신호로도 후보를
            # 못 찾은 경우("apartment_type_missing")를 구분한다 -- 관리자
            # 화면에서 "타입을 새로 찾아야 함"과 "여러 후보 중 골라야 함"은
            # 처리 방법이 다르다.
            review_reasons.append(
                "apartment_type_ambiguous" if apartment_type_ambiguous else "apartment_type_missing"
            )
        review_reason = ",".join(review_reasons) or None
        repository.finalize_import_portfolio(
            session,
            portfolio_id=portfolio_id,
            # 신뢰도가 기준값 미만이거나 관리자가 체크 해제했으면
            # publish_immediately와 무관하게 'pending'(검수 대기)으로 남긴다.
            publish_immediately=bool(job["options"].get("publish_immediately", True)) and publish_ok,
            published_at=item.get("created_at"),
            review_reason=review_reason,
        )
        previous_result = dict(
            repository.find_record(
                session,
                job_id=job_id,
                record_id=record_id,
            )["result"]
            or {}
        )
        result = {
            **previous_result,
            "company_id": company_id,
            "complex_id": complex_id,
            "apartment_type_id": apartment_type_id,
            "review_reason": review_reason,
            # v2.5.0: content_blocks_from_item이 원문 재현 텍스트에서 지운
            # 플랫폼 문구/홍보 헤딩 개수. previous_result에 이미 있던(초반
            # 레코드 생성 시 confidence 파이프라인이 남긴) 값에 더한다 --
            # 이 JSON은 paragraphs가 없어 confidence 쪽은 항상 0이지만,
            # 나중에 두 파이프라인이 같이 도는 소스가 생겨도 합산되게 둔다.
            "platform_mentions_removed": (
                previous_result.get("platform_mentions_removed") or 0
            ) + content_blocks_stats.get("platform_mentions_removed", 0),
            "receipt_titles_normalized": content_blocks_stats.get(
                "receipt_titles_normalized", 0
            ),
            # v2.5.1: 본문(content_blocks)에 나오는 사진 중 우리 서버로
            # 옮겨진 개수 / 여전히 외부 CDN으로 남은 개수(MAX_IMAGES_PER_
            # PORTFOLIO 절대 상한을 넘어선 극소수 케이스만 여기 남는다).
            "content_blocks_images_localized": content_blocks_stats.get(
                "images_localized_count", 0
            ),
            "content_blocks_images_still_external": content_blocks_stats.get(
                "images_still_external_count", 0
            ),
            "image_success_count": image_success,
            "image_failed_count": image_failed,
            "image_limit_excluded_count": max(
                0,
                sum(
                    str(image.get("phase") or "").strip().upper() == "AFTER"
                    for image in item.get("images") or []
                ) - len(selected_images),
            ),
            "before_image_excluded_count": sum(
                str(image.get("phase") or "").strip().upper() == "BEFORE"
                for image in item.get("images") or []
            ),
        }
        repository.update_record(
            session,
            record_id=record_id,
            changes={
                "status": "succeeded",
                "target_id": portfolio_id,
                "result": result,
                "error_message": None if not image_failed else f"이미지 {image_failed}장 다운로드 실패",
            },
        )
        session.execute(text("""
            UPDATE bulk_import_jobs
            SET image_success_count=image_success_count+:success,
                image_failed_count=image_failed_count+:failed,
                updated_at=NOW()
            WHERE id=:job_id
        """), {"success": image_success, "failed": image_failed, "job_id": job_id})
        session.commit()


def _load_company_portfolio_source(job: dict[str, Any]) -> dict[str, Any]:
    """Load the uploaded file into the shared {'companies', 'portfolios'}
    shape, regardless of whether the admin uploaded JSON or the richer Excel
    workbook -- everything downstream (company creation, complex matching,
    space grouping, image download) works on that one shape either way."""
    source_path = Path(job["source_path"])
    if job["job_type"] == "company_portfolio_excel":
        return load_portfolio_workbook(source_path)
    with source_path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def _process_company_portfolio_job(job: dict[str, Any]) -> None:
    data = _load_company_portfolio_source(job)
    company_sources: dict[str, dict[str, Any]] = {}
    for company in data.get("companies") or []:
        key = str(company.get("writer_id") or company.get("expert_id") or "").strip()
        if key:
            company_sources[key] = company
    with SessionLocal() as session:
        selected_records = repository.list_records(
            session,
            job_id=job["id"],
            status=None,
            limit=10_000,
            offset=0,
        )
    selected_keys = {
        str(record["record_key"])
        for record in selected_records
        if record["record_type"] == "portfolio"
    }
    expert_portfolios = [
        item for item in data.get("portfolios") or []
        if str(item.get("agent") or "").strip() == "전문가"
        and str(item.get("portfolio_id") or "").strip() in selected_keys
    ]
    for item in expert_portfolios:
        if _job_cancelled(job["id"]):
            return
        try:
            _process_json_portfolio(job, item, company_sources)
        except Exception as exc:
            logger.exception("업체·포트폴리오 일괄등록 실패", extra={"job_id": job["id"]})
            source_key = str(item.get("portfolio_id") or f"unknown-{id(item)}")
            with SessionLocal() as session:
                record_id = repository.create_record(
                    session,
                    job_id=job["id"],
                    record_type="portfolio",
                    record_key=source_key,
                    source_label=_text(item.get("title"), 500),
                    payload={"portfolio_id": source_key},
                    status="failed",
                    error_message=str(exc)[:2000],
                )
                if record_id is None:
                    rows = repository.list_records(
                        session, job_id=job["id"], status=None, limit=10_000, offset=0
                    )
                    existing = next((row for row in rows if row["record_key"] == source_key), None)
                    if existing:
                        repository.update_record(
                            session,
                            record_id=existing["id"],
                            changes={"status": "failed", "error_message": str(exc)[:2000]},
                        )
                session.commit()
        _sync_job_counts(job["id"])
    with SessionLocal() as session:
        finished_records = repository.list_records(
            session,
            job_id=job["id"],
            status=None,
            limit=10_000,
            offset=0,
        )
    created_complexes = list(dict.fromkeys(
        str(record["result"].get("complex_name"))
        for record in finished_records
        if record["result"].get("complex_created")
        and record["result"].get("complex_name")
    ))
    naver_failed_names = list(dict.fromkeys(
        str(record["result"].get("complex_name"))
        for record in finished_records
        if record["result"].get("complex_created")
        and record["result"].get("complex_naver_collected") is False
        and record["result"].get("complex_name")
    ))
    if naver_failed_names:
        with SessionLocal() as session:
            NotificationService.create(
                session,
                user_id=job["requested_by"],
                notification_type="bulk_complex_naver_failed",
                title=f"포트폴리오 단지 네이버 확인 실패 {len(naver_failed_names)}건",
                message=(
                    "주소 기본정보만 등록한 단지: "
                    + ", ".join(naver_failed_names[:100])
                ),
                target_type="bulk_import_job",
                target_id=job["id"],
            )
            session.commit()
    _finish_job(
        job["id"],
        summary_updates={
            "created_complex_names": created_complexes,
            "naver_failed_names": naver_failed_names,
        },
    )
    # v2.5.1 (2026-08-22, 사용자 지시 "대량등록 완료 시 자동으로 이어서"):
    # structured 필드가 비어 단지/타입을 못 찾은 포트폴리오를 title
    # 텍스트 마이닝으로 한 번 더 시도한다. 등록 자체를 지연시키지 않도록
    # _finish_job으로 본 결과를 먼저 확정한 뒤 이어서 실행 -- 마이닝이
    # 실패해도(네트워크 문제 등) 본 등록 결과에는 영향 없어야 하므로
    # 예외를 여기서 잡아 로그만 남긴다. worker.py 상단에서 import하면
    # title_mining.py가 다시 worker의 _ensure_portfolio_complex를 쓰는
    # 순환 import가 생겨서 함수 안에서 지역 import.
    try:
        from app.modules.bulk_import.title_mining import (
            mine_unresolved_portfolios_for_job,
        )
        mining_stats = mine_unresolved_portfolios_for_job(
            job["id"], admin_user_id=job["requested_by"]
        )
        logger.info(
            "대량등록 후속 title 마이닝 결과: job_id=%s %s",
            job["id"], mining_stats,
        )
    except Exception:
        logger.exception(
            "대량등록 후속 title 마이닝 중 오류(본 등록 결과에는 영향 없음)",
            extra={"job_id": job["id"]},
        )


def _run_job(job: dict[str, Any]) -> None:
    with SessionLocal() as session:
        repository.update_job(
            session,
            job_id=job["id"],
            changes={"status": "running", "error_message": None},
        )
        session.execute(
            text("UPDATE bulk_import_jobs SET started_at=COALESCE(started_at,NOW()) WHERE id=:job_id"),
            {"job_id": job["id"]},
        )
        session.commit()
    if job["job_type"] == "complex_excel":
        _process_complex_job(job)
    else:
        _process_company_portfolio_job(job)


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
                    logger.exception("일괄등록 작업 중단", extra={"job_id": job["id"]})
                    with SessionLocal() as session:
                        repository.update_job(
                            session,
                            job_id=job["id"],
                            changes={"status": "failed", "error_message": str(exc)[:2000]},
                        )
                        session.execute(
                            text("UPDATE bulk_import_jobs SET completed_at=NOW() WHERE id=:job_id"),
                            {"job_id": job["id"]},
                        )
                        session.commit()
            else:
                time.sleep(2)
        except Exception:
            logger.exception("일괄등록 worker polling 오류")
            time.sleep(5)


def start_bulk_import_worker() -> None:
    """단일 uvicorn 프로세스에서 한 worker만 시작하고 재기동 시 running 작업을 잇는다."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop,
            name="zipterior-bulk-import",
            daemon=True,
        )
        thread.start()
        _worker_started = True
