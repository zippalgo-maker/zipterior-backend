import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


JOB_COLUMNS = """
    id, job_type, status, original_filename, source_path,
    expected_size, uploaded_size, options, summary,
    total_count, resolved_count, processed_count, success_count,
    duplicate_count, failed_count, skipped_count,
    image_success_count, image_failed_count, error_message,
    requested_by, notification_sent, created_at, started_at,
    completed_at, updated_at
"""

# v2.5.60(2026-08-24): success_count는 worker.py가 단지/타입을 못 찾아
# review_reason이 붙은("확인필요") 레코드도 status='succeeded'로 같이
# 세서 늘어난다(등록 자체는 성공했으니까) -- 그래서 관리자 화면 "보기"의
# 결과 목록(개별 행)은 review_reason 있으면 "확인필요"로 따로 보여주는데,
# 요약 카드의 "성공" 숫자는 그 확인필요분까지 합쳐진 채였다(사용자
# 리포트: "성공 숫자가 안 맞아" -- 목록에서 "성공"이라고 적힌 행 수를
# 세면 요약의 "성공"보다 항상 적었던 게 바로 이 차이). success_count
# 컬럼 자체의 의미는 그대로 두고(다른 코드가 이미 "등록 성공 전체"로
# 씀), 대신 review_count를 서브쿼리로 같이 내려줘서 프론트가
# 성공(순수) = success_count - review_count로 분리해 보여줄 수 있게
# 한다. idx_bulk_import_records_job_status(job_id,status,id) 인덱스가
# 이미 있어 job_id+status 필터까지는 인덱스를 타고, result JSONB
# 조건만 남은 행들에서 걸러진다(job 하나당 레코드 수가 보통 수백~
# 수천 건이라 순차 스캔이어도 감당됨).
JOB_REVIEW_COUNT_SUBQUERY = """
    (SELECT COUNT(*) FROM bulk_import_records r
     WHERE r.job_id = bulk_import_jobs.id
       AND r.status = 'succeeded'
       AND r.result->>'review_reason' IS NOT NULL
    ) AS review_count
"""


def create_job(
    session: Session,
    *,
    job_type: str,
    filename: str,
    expected_size: int,
    options: dict[str, Any],
    requested_by: int,
) -> int:
    return int(session.execute(text("""
        INSERT INTO bulk_import_jobs (
            job_type, original_filename, expected_size, options, requested_by
        ) VALUES (
            :job_type, :filename, :expected_size, CAST(:options AS jsonb), :requested_by
        ) RETURNING id
    """), {
        "job_type": job_type,
        "filename": filename,
        "expected_size": expected_size,
        "options": json.dumps(options, ensure_ascii=False),
        "requested_by": requested_by,
    }).scalar_one())


def find_job(session: Session, *, job_id: int, requested_by: int | None = None) -> dict[str, Any] | None:
    where = "id=:job_id" + (" AND requested_by=:requested_by" if requested_by else "")
    row = session.execute(text(f"SELECT {JOB_COLUMNS}, {JOB_REVIEW_COUNT_SUBQUERY} FROM bulk_import_jobs WHERE {where}"), {
        "job_id": job_id,
        "requested_by": requested_by,
    }).mappings().one_or_none()
    return dict(row) if row else None


def lock_job(session: Session, *, job_id: int, requested_by: int) -> dict[str, Any] | None:
    row = session.execute(text(f"""
        SELECT {JOB_COLUMNS}
        FROM bulk_import_jobs
        WHERE id=:job_id AND requested_by=:requested_by
        FOR UPDATE
    """), {"job_id": job_id, "requested_by": requested_by}).mappings().one_or_none()
    return dict(row) if row else None


def list_jobs(session: Session, *, requested_by: int, limit: int) -> list[dict[str, Any]]:
    # v2.5.44(2026-08-23): 화면엔 "최근 작업이 위"(역순)가 아니라 만든
    # 순서 그대로 보여달라는 요청 -- 그렇다고 전체 이력을 그냥
    # 오름차순+LIMIT으로 뽑으면 오래된 :limit건만 잘려 나오고 정작
    # 최근 작업이 안 보이게 된다. 그래서 "최근 :limit건을 먼저 뽑고,
    # 그 안에서는 생성순으로 다시 정렬"하도록 서브쿼리로 감쌌다.
    rows = session.execute(text(f"""
        SELECT * FROM (
            SELECT {JOB_COLUMNS}, {JOB_REVIEW_COUNT_SUBQUERY}
            FROM bulk_import_jobs
            WHERE requested_by=:requested_by
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
        ) recent_jobs
        ORDER BY created_at ASC, id ASC
    """), {"requested_by": requested_by, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def update_job(session: Session, *, job_id: int, changes: dict[str, Any]) -> None:
    allowed = {
        "status", "source_path", "uploaded_size", "options", "summary",
        "total_count", "resolved_count", "processed_count", "success_count",
        "duplicate_count", "failed_count", "skipped_count",
        "image_success_count", "image_failed_count", "error_message",
        "notification_sent", "started_at", "completed_at",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return
    assignments = []
    params: dict[str, Any] = {"job_id": job_id}
    for key, value in values.items():
        if key in {"options", "summary"}:
            assignments.append(f"{key}=CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value, ensure_ascii=False)
        else:
            assignments.append(f"{key}=:{key}")
            params[key] = value
    assignments.append("updated_at=NOW()")
    session.execute(text(f"UPDATE bulk_import_jobs SET {', '.join(assignments)} WHERE id=:job_id"), params)


def create_record(
    session: Session,
    *,
    job_id: int,
    record_type: str,
    record_key: str,
    source_label: str | None,
    payload: dict[str, Any],
    status: str = "pending",
    error_message: str | None = None,
) -> int | None:
    return session.execute(text("""
        INSERT INTO bulk_import_records (
            job_id, record_type, record_key, source_label, payload, status, error_message
        ) VALUES (
            :job_id, :record_type, :record_key, :source_label,
            CAST(:payload AS jsonb), :status, :error_message
        )
        ON CONFLICT (job_id, record_type, record_key) DO NOTHING
        RETURNING id
    """), {
        "job_id": job_id,
        "record_type": record_type,
        "record_key": record_key,
        "source_label": source_label,
        "payload": json.dumps(payload, ensure_ascii=False),
        "status": status,
        "error_message": error_message,
    }).scalar_one_or_none()


def list_records(
    session: Session,
    *,
    job_id: int,
    status: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    status_filter = " AND status=:status" if status else ""
    rows = session.execute(text(f"""
        SELECT id, job_id, record_type, record_key, source_label, status,
               payload, result, target_id, error_message
        FROM bulk_import_records
        WHERE job_id=:job_id{status_filter}
        ORDER BY id
        LIMIT :limit OFFSET :offset
    """), {"job_id": job_id, "status": status, "limit": limit, "offset": offset}).mappings().all()
    return [dict(row) for row in rows]


# 2026-08-25: 상세 화면 결과/검수 목록에 페이지네이션을 붙이기 위한 총
# 건수 조회 -- list_records(위)는 worker.py 등 내부 처리 루프가 그대로
# 직접 호출하므로 반환 타입을 안 건드리고, 페이지네이션이 필요한 라우터
# 쪽(BulkImportService.list_records)에서만 이 함수를 같이 써서
# (items, total)로 감싼다.
def count_records(session: Session, *, job_id: int, status: str | None) -> int:
    status_filter = " AND status=:status" if status else ""
    return int(session.execute(text(f"""
        SELECT COUNT(*) FROM bulk_import_records
        WHERE job_id=:job_id{status_filter}
    """), {"job_id": job_id, "status": status}).scalar_one())


def find_record(session: Session, *, job_id: int, record_id: int) -> dict[str, Any] | None:
    row = session.execute(text("""
        SELECT id, job_id, record_type, record_key, source_label, status,
               payload, result, target_id, error_message
        FROM bulk_import_records
        WHERE job_id=:job_id AND id=:record_id
    """), {"job_id": job_id, "record_id": record_id}).mappings().one_or_none()
    return dict(row) if row else None


def update_record(session: Session, *, record_id: int, changes: dict[str, Any]) -> None:
    allowed = {"status", "payload", "result", "target_id", "error_message", "source_label"}
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return
    assignments = []
    params: dict[str, Any] = {"record_id": record_id}
    for key, value in values.items():
        if key in {"payload", "result"}:
            assignments.append(f"{key}=CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value, ensure_ascii=False)
        else:
            assignments.append(f"{key}=:{key}")
            params[key] = value
    assignments.append("updated_at=NOW()")
    session.execute(text(f"UPDATE bulk_import_records SET {', '.join(assignments)} WHERE id=:record_id"), params)


def record_status_counts(session: Session, *, job_id: int) -> dict[str, int]:
    rows = session.execute(text("""
        SELECT status, COUNT(*) AS count
        FROM bulk_import_records WHERE job_id=:job_id GROUP BY status
    """), {"job_id": job_id}).all()
    return {str(status): int(count) for status, count in rows}


def source_target(session: Session, *, source_system: str, entity_type: str, source_key: str) -> int | None:
    value = session.execute(text("""
        SELECT target_id FROM source_import_links
        WHERE source_system=:source_system AND entity_type=:entity_type AND source_key=:source_key
    """), {
        "source_system": source_system,
        "entity_type": entity_type,
        "source_key": source_key,
    }).scalar_one_or_none()
    return int(value) if value is not None else None


def create_source_link(
    session: Session,
    *,
    source_system: str,
    entity_type: str,
    source_key: str,
    target_id: int,
    metadata: dict[str, Any],
) -> None:
    session.execute(text("""
        INSERT INTO source_import_links (
            source_system, entity_type, source_key, target_id, metadata
        ) VALUES (
            :source_system, :entity_type, :source_key, :target_id, CAST(:metadata AS jsonb)
        )
        ON CONFLICT (source_system, entity_type, source_key) DO NOTHING
    """), {
        "source_system": source_system,
        "entity_type": entity_type,
        "source_key": source_key,
        "target_id": target_id,
        "metadata": json.dumps(metadata, ensure_ascii=False),
    })


def next_runnable_job(session: Session) -> dict[str, Any] | None:
    row = session.execute(text(f"""
        SELECT {JOB_COLUMNS}
        FROM bulk_import_jobs
        WHERE status IN ('queued', 'running')
        ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, created_at, id
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """)).mappings().one_or_none()
    return dict(row) if row else None


def find_company_for_import(
    session: Session,
    *,
    name: str,
    address: str | None,
    business_number: str | None,
) -> int | None:
    value = session.execute(text("""
        SELECT id
        FROM companies
        WHERE deleted_at IS NULL
          AND (
              (
                  NULLIF(TRIM(:business_number), '') IS NOT NULL
                  AND REGEXP_REPLACE(COALESCE(business_number, ''), '[^0-9]', '', 'g')
                      = REGEXP_REPLACE(:business_number, '[^0-9]', '', 'g')
              )
              OR (
                  NULLIF(TRIM(:address), '') IS NOT NULL
                  AND
                  LOWER(REGEXP_REPLACE(name, '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:name, '[^0-9A-Za-z가-힣]', '', 'g'))
                  AND LOWER(REGEXP_REPLACE(COALESCE(address, ''), '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:address, '[^0-9A-Za-z가-힣]', '', 'g'))
              )
          )
        ORDER BY
            CASE
                WHEN NULLIF(TRIM(:business_number), '') IS NOT NULL
                 AND REGEXP_REPLACE(COALESCE(business_number, ''), '[^0-9]', '', 'g')
                     = REGEXP_REPLACE(:business_number, '[^0-9]', '', 'g')
                THEN 0 ELSE 1
            END,
            id
        LIMIT 1
    """), {
        "name": name,
        "address": address,
        "business_number": business_number,
    }).scalar_one_or_none()
    return int(value) if value is not None else None


def create_import_company(
    session: Session,
    *,
    admin_user_id: int,
    source_key: str,
    values: dict[str, Any],
    publish_immediately: bool,
) -> int:
    status = "active" if publish_immediately else "pending"
    # 동일한 status 바인드값을 VARCHAR 컬럼과 CASE 비교식에 함께 쓰면 psycopg가
    # text/varchar 타입을 서로 다르게 추론한다. 공개 여부는 bool 매개변수로 분리해
    # 업체 생성 SQL의 자료형을 한 가지로 확정한다(기존 중복 CASE 방식 대체).
    return int(session.execute(text("""
        INSERT INTO companies (
            owner_user_id, name, slug, business_number, representative_name,
            phone, email, address, intro, website_url, status,
            consultation_available, is_visible_on_map, approved_at, approved_by
        ) VALUES (
            NULL, :name, :slug, :business_number, :representative_name,
            :phone, :email, :address, :intro, :website_url, :status,
            TRUE, FALSE,
            CASE WHEN :publish_immediately THEN NOW() ELSE NULL END,
            CASE WHEN :publish_immediately THEN :admin_user_id ELSE NULL END
        ) RETURNING id
    """), {
        "name": values["name"],
        "slug": f"ohou-{source_key}"[:200],
        "business_number": values.get("business_number"),
        "representative_name": values.get("representative_name"),
        "phone": values.get("phone"),
        "email": values.get("email"),
        "address": values.get("address"),
        "intro": values.get("intro"),
        "website_url": values.get("website_url"),
        "status": status,
        "publish_immediately": publish_immediately,
        "admin_user_id": admin_user_id,
    }).scalar_one())


def find_complex_for_import(
    session: Session,
    *,
    name: str | None,
    road_address: str | None,
    sigungu: str | None = None,
) -> dict[str, Any] | None:
    """실측 확인된 버그(2026-08-22, title 마이닝 검증 중 발견): 예전엔
    이름만 같으면(주소가 전혀 달라도) 같은 단지로 취급했다 -- "현대아파트",
    "삼성아파트", "주공아파트"처럼 전국에 흔한 이름이 실제로 서로 다른
    도시에 여러 개 있는데, 남양주 오남읍의 "현대아파트" 포트폴리오가
    서울 동작구의 "현대아파트"(이름만 같음, 주소는 완전히 다름)에
    잘못 연결되는 사고가 실제로 재현됨. 이제는 도로명주소가 정확히
    일치하는 경우만 무조건 같은 단지로 보고, 이름만 같은 경우는
    `sigungu`(시군구)까지 같이 일치해야 같은 단지로 본다 -- sigungu를
    모르는 상태(예: 주소 확인 전 최초 조회)에서는 이름만으로는 아예
    매칭하지 않는다(모르면 새로 만드는 쪽이 안전 -- 틀린 기존 단지에
    잘못 붙는 것보다 낫다)."""
    row = session.execute(text("""
        SELECT id, name
        FROM apartment_complexes
        WHERE is_active=TRUE
          AND (
              (
                  NULLIF(TRIM(:road_address), '') IS NOT NULL
                  AND LOWER(REGEXP_REPLACE(COALESCE(road_address, ''), '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:road_address, '[^0-9A-Za-z가-힣]', '', 'g'))
              )
              OR (
                  NULLIF(TRIM(:name), '') IS NOT NULL
                  AND LOWER(REGEXP_REPLACE(name, '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:name, '[^0-9A-Za-z가-힣]', '', 'g'))
                  AND NULLIF(TRIM(:sigungu), '') IS NOT NULL
                  AND LOWER(REGEXP_REPLACE(COALESCE(sigungu, ''), '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:sigungu, '[^0-9A-Za-z가-힣]', '', 'g'))
              )
          )
        ORDER BY CASE WHEN road_address IS NOT NULL AND :road_address IS NOT NULL THEN 0 ELSE 1 END, id
        LIMIT 1
    """), {"name": name, "road_address": road_address, "sigungu": sigungu}).mappings().one_or_none()
    return dict(row) if row else None


_TYPE_TOKEN_RE = re.compile(r"[^0-9A-Za-z가-힣]")
# pyeong_label 끝에 붙는 타입 구분용 영문자(예: "21A" -> "21")만 떼어낸다.
# _normalize_type_token()이 이미 소문자로 바꾼 뒤 문자열이라 소문자만 처리.
_TRAILING_LETTERS_RE = re.compile(r"[a-z]+$")


def _normalize_type_token(value: Any) -> str:
    return _TYPE_TOKEN_RE.sub("", str(value or "")).strip().lower()


def _pyeong_label_candidates(value: Any) -> list[str]:
    """숫자 평형값(예: 43, '43평', 43.0)에서 pyeong_label과 비교할 후보
    문자열들을 만든다(둘 다 정규화 후 비교하지만, '평' 유무 차이는
    정규화 정규식이 숫자/문자만 남기므로 이미 흡수됨 -- 그래도 원본
    형태 그대로도 후보에 넣어 만약을 대비한다).

    v5.3의 real_area_pyeong은 못 찾았을 때 빈 값 대신 0을 채워 넣는
    경우가 있다(이번 파일 기준 427건 중 5건) -- 0평은 실존하지 않으므로
    "값 없음"으로 취급해 헛매칭을 시도하지 않는다."""
    text_value = str(value if value is not None else "").strip()
    if not text_value:
        return []
    try:
        as_float = float(text_value.replace("평", ""))
    except (TypeError, ValueError):
        as_float = None
    if as_float == 0:
        return []
    candidates = {text_value}
    if as_float is not None:
        as_int = int(as_float)
        candidates.add(str(as_int))
        candidates.add(f"{as_int}평")
    return [c for c in candidates if c]


def resolve_type_for_import(
    session: Session,
    *,
    complex_id: int,
    item: dict[str, Any],
) -> tuple[int | None, bool]:
    """단지의 apartment_types 중 이 포트폴리오에 맞는 타입을 찾는다.
    (2026-08-22, 사용자가 전달한 v5.3 필드 우선순위 규칙 문서 기준으로
    기존 find_type_for_import를 대체)

    우선순위:
    1. area_id -- 크롤러 원본 식별자. `해시-타입명`(예:
       "62208f8ba3677b4bcfb56e37-101A") 형태가 흔해 마지막 '-' 뒤만
       떼어 비교한다. "no-apartment-"처럼 타입명이 아닌 값은 실제
       type_name과 우연히 일치하지 않는 한 자연히 걸러지므로 별도
       검증 로직 불필요.
    2. area_type_structured (구조화 필드)
    3. area_type
    4. area_type_text_detected (본문에서 텍스트로만 감지, 가장 약한 신호)
    5. 위 네 단계 모두 실패하면 real_area_pyeong -> area_pyeong 순으로
       평형(pyeong_label) 매칭

    각 단계에서 후보가 정확히 1개면 확정, 0개면 다음 단계로, **2개
    이상이면 임의로 고르지 않고 (None, True)를 반환**(사용자 규칙
    7-8번: "후보가 여러 개면 임의로 선택하지 않는다" -- 강한 신호에서
    이미 모호하면 더 약한 신호로 넘어가도 좁혀지지 않는다고 보고 즉시
    멈춘다). 반환값의 두 번째 값(ambiguous)이 True면 worker.py가
    review_reason에 'apartment_type_ambiguous'를 남긴다(기존
    'apartment_type_missing'과 구분 -- 못 찾은 것과 후보가 여러 개라
    확정 못 한 것은 관리자 처리 방법이 다르다).
    """
    rows = session.execute(text("""
        SELECT id, type_name, pyeong_label
        FROM apartment_types
        WHERE complex_id=:complex_id
        ORDER BY sort_order, id
    """), {"complex_id": complex_id}).mappings().all()
    if not rows:
        return None, False

    def by_type_name(raw: Any) -> list[Any]:
        target = _normalize_type_token(raw)
        if not target:
            return []
        return [r for r in rows if _normalize_type_token(r["type_name"]) == target]

    def by_pyeong(raw: Any) -> list[Any]:
        for label in _pyeong_label_candidates(raw):
            target = _normalize_type_token(label)
            if not target:
                continue
            matched = [r for r in rows if _normalize_type_token(r["pyeong_label"]) == target]
            if matched:
                return matched
            # 실측 확인(2026-08-22, job#33 427건 등록 후): 전체 apartment_types의
            # 55.5%가 pyeong_label에 타입 구분용 글자가 붙어있다(예: "21A"/"21B"
            # 처럼 같은 평형에 레이아웃만 다른 경우). 이때 위의 완전일치 비교는
            # "21"과 "21A"가 달라서 항상 0건으로 실패하고, 실제로는 후보가 여러
            # 개(21A/21B) 있는데도 "못 찾음"으로만 남아버린다("모호함"이 한 번도
            # 안 뜨던 원인). pyeong_label 뒤에 붙은 글자를 떼고 숫자부분만 다시
            # 비교해서, 여러 개 걸리면 그대로 위 resolve_type_for_import의
            # "후보 2개 이상 -> 모호함" 처리로 넘긴다(letter 하나로 자동 확정하지
            # 않음 -- 여전히 임의 선택 금지 원칙 유지).
            bare_matched = [
                r for r in rows
                if _TRAILING_LETTERS_RE.sub("", _normalize_type_token(r["pyeong_label"])) == target
            ]
            if bare_matched:
                return bare_matched
        return []

    area_id_raw = item.get("area_id")
    area_id_suffix = (
        str(area_id_raw).rsplit("-", 1)[-1]
        if area_id_raw and "-" in str(area_id_raw)
        else area_id_raw
    )

    for candidate_fn, raw_value in (
        (by_type_name, area_id_suffix),
        (by_type_name, item.get("area_type_structured")),
        (by_type_name, item.get("area_type")),
        (by_type_name, item.get("area_type_text_detected")),
    ):
        candidates = candidate_fn(raw_value)
        if len(candidates) == 1:
            return int(candidates[0]["id"]), False
        if len(candidates) > 1:
            return None, True

    for pyeong_value in (item.get("real_area_pyeong"), item.get("area_pyeong")):
        candidates = by_pyeong(pyeong_value)
        if len(candidates) == 1:
            return int(candidates[0]["id"]), False
        if len(candidates) > 1:
            return None, True

    return None, False


def create_import_portfolio(
    session: Session,
    *,
    admin_user_id: int,
    company_id: int,
    values: dict[str, Any],
    publish_immediately: bool,
) -> int:
    # 이미지는 기존 편집 가능 상태 규칙을 그대로 통과시킨 뒤 worker가 최종 상태를 확정한다.
    status = "draft"
    return int(session.execute(text("""
        INSERT INTO portfolios (
            company_id, complex_id, apartment_type_id, created_by_user_id,
            registration_source, title, summary, description,
            construction_scope, budget_min, budget_max, construction_days,
            construction_date, status, published_at
        ) VALUES (
            :company_id, :complex_id, :apartment_type_id, :admin_user_id,
            'admin_proxy', :title, :summary, :description,
            :construction_scope, :budget_min, :budget_max, :construction_days,
            :construction_date, :status,
            NULL
        ) RETURNING id
    """), {
        "company_id": company_id,
        "complex_id": values.get("complex_id"),
        "apartment_type_id": values.get("apartment_type_id"),
        "admin_user_id": admin_user_id,
        "title": values["title"],
        "summary": values.get("summary"),
        "description": values.get("description"),
        "construction_scope": values.get("construction_scope"),
        "budget_min": values.get("budget_min"),
        "budget_max": values.get("budget_max"),
        "construction_days": values.get("construction_days"),
        "construction_date": values.get("construction_date"),
        "status": status,
        "published_at": values.get("published_at"),
    }).scalar_one())


def create_import_space(
    session: Session,
    *,
    portfolio_id: int,
    space_code: str,
    space_name: str,
    space_number: int,
    description: str | None,
    sort_order: int,
) -> int:
    return int(session.execute(text("""
        INSERT INTO portfolio_spaces (
            portfolio_id, space_code, space_name, space_number, description, sort_order
        ) VALUES (
            :portfolio_id, :space_code, :space_name, :space_number, :description, :sort_order
        ) RETURNING id
    """), {
        "portfolio_id": portfolio_id,
        "space_code": space_code,
        "space_name": space_name,
        "space_number": space_number,
        "description": description,
        "sort_order": sort_order,
    }).scalar_one())


def find_import_portfolio(session: Session, *, portfolio_id: int) -> dict[str, Any] | None:
    # complex_id/apartment_type_id도 함께 읽는다 -- 중단된 작업을 이어받는
    # "linked" 경로(worker.py)가 이전 실행 결과(bulk_import_records.result)에
    # 의존하지 않고 실제 포트폴리오 행에서 바로 확인하도록 하기 위함(v2.5.0).
    row = session.execute(text("""
        SELECT id, company_id, status, complex_id, apartment_type_id
        FROM portfolios
        WHERE id=:portfolio_id AND deleted_at IS NULL
    """), {"portfolio_id": portfolio_id}).mappings().one_or_none()
    return dict(row) if row else None


def import_spaces(
    session: Session,
    *,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    """Return ordered spaces so a resumed import can verify its exact structure."""
    rows = session.execute(text("""
        SELECT id, space_code, space_name, space_number, sort_order
        FROM portfolio_spaces
        WHERE portfolio_id=:portfolio_id
        ORDER BY sort_order, id
    """), {
        "portfolio_id": portfolio_id,
    }).mappings().all()
    return [dict(row) for row in rows]


def finalize_import_portfolio(
    session: Session,
    *,
    portfolio_id: int,
    publish_immediately: bool,
    published_at: Any,
    review_reason: str | None = None,
) -> None:
    """v2.5.0: `review_reason`이 있으면(예: 단지를 못 찾아 지도 마커를 못 꽂는
    경우) 신뢰도 판정/publish_immediately와 무관하게 status='draft'로 남긴다.
    'draft'는 업체가 기존 수정 화면에서 그대로 고쳐서 제출할 수 있는 상태라서
    -- 'pending'/'approved'로 마무리해버리면 업체가 고칠 방법이 없어진다
    (portfolios/service.py의 update_portfolio가 draft/rejected/hidden만
    수정 허용). review_reason이 없으면 기존과 동일하게 approved/pending으로
    마무리하고, 혹시 남아있을 이전 사유는 정리 차원에서 NULL로 비운다."""
    if review_reason:
        session.execute(text("""
            UPDATE portfolios
            SET status='draft',
                published_at=NULL,
                review_reason=:review_reason,
                updated_at=NOW()
            WHERE id=:portfolio_id AND deleted_at IS NULL
        """), {
            "portfolio_id": portfolio_id,
            "review_reason": review_reason,
        })
        return
    session.execute(text("""
        UPDATE portfolios
        SET status=CASE WHEN :publish THEN 'approved' ELSE 'pending' END,
            published_at=CASE WHEN :publish THEN COALESCE(CAST(:published_at AS timestamptz), NOW()) ELSE NULL END,
            review_reason=NULL,
            updated_at=NOW()
        WHERE id=:portfolio_id AND deleted_at IS NULL
    """), {
        "portfolio_id": portfolio_id,
        "publish": publish_immediately,
        "published_at": published_at,
    })


def replace_content_blocks(
    session: Session,
    *,
    portfolio_id: int,
    blocks: list[dict[str, Any]],
) -> int:
    """v2.5.0 (테스트, additive): 원문 순서 재현용 블록을 전부 지우고
    다시 넣는다. 이 포트폴리오의 확정 데이터가 아니라 재실행 가능한
    테스트 스냅샷이라 delete+insert가 upsert보다 단순하고 안전하다
    (일괄등록을 다시 돌리면 최신 크롤링 결과로 그대로 갱신됨)."""
    session.execute(
        text("DELETE FROM portfolio_content_blocks WHERE portfolio_id=:portfolio_id"),
        {"portfolio_id": portfolio_id},
    )
    if not blocks:
        return 0
    session.execute(
        text("""
            INSERT INTO portfolio_content_blocks (
                portfolio_id, document_order, node_type, block_type,
                text_content, image_url, image_width, image_height,
                raw_node, metadata_json
            ) VALUES (
                :portfolio_id, :document_order, :node_type, :block_type,
                :text_content, :image_url, :image_width, :image_height,
                CAST(:raw_node AS jsonb), CAST(:metadata_json AS jsonb)
            )
        """),
        [
            {
                "portfolio_id": portfolio_id,
                "document_order": b["document_order"],
                "node_type": b["node_type"],
                "block_type": b["block_type"],
                "text_content": b["text_content"],
                "image_url": b["image_url"],
                "image_width": b["image_width"],
                "image_height": b["image_height"],
                "raw_node": json.dumps(b["raw_node"], ensure_ascii=False),
                "metadata_json": json.dumps(b["metadata_json"], ensure_ascii=False),
            }
            for b in blocks
        ],
    )
    return len(blocks)


def local_image_urls_for_source(
    session: Session, *, portfolio_source_key: str
) -> dict[str, str]:
    """v2.5.1: content_blocks의 image_url을 원본(외부 CDN) 대신 우리 서버
    경로로 재작성하기 위한 매핑. 이 포트폴리오의 이미지 다운로드 루프가
    source_import_links에 남긴 원본 image_url -- portfolio_images.id 연결을
    타고 large_path까지 조인해서 {원본 image_url: 우리 서버 large_path}
    딕셔너리로 돌려준다. 아직 로컬에 없는(예: 한도 초과로 스킵된) 이미지는
    이 딕셔너리에 없다 -- 호출하는 쪽이 원본 URL을 그대로 둘지 판단한다."""
    rows = session.execute(
        text("""
            SELECT l.metadata->>'image_url' AS image_url, pi.large_path
            FROM source_import_links l
            JOIN portfolio_images pi ON pi.id = l.target_id
            WHERE l.entity_type = 'portfolio_image'
              AND l.metadata->>'portfolio_source_key' = :portfolio_source_key
              AND l.metadata->>'image_url' IS NOT NULL
              AND pi.large_path IS NOT NULL
        """),
        {"portfolio_source_key": portfolio_source_key},
    ).all()
    return {row.image_url: row.large_path for row in rows}


def has_content_blocks(session: Session, *, portfolio_ids: list[int]) -> set[int]:
    if not portfolio_ids:
        return set()
    rows = session.execute(
        text("""
            SELECT DISTINCT portfolio_id FROM portfolio_content_blocks
            WHERE portfolio_id = ANY(:ids)
        """),
        {"ids": portfolio_ids},
    ).scalars().all()
    return set(rows)


def list_content_blocks(session: Session, *, portfolio_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text("""
            SELECT id, document_order, node_type, block_type, text_content,
                   image_url, image_width, image_height, raw_node
            FROM portfolio_content_blocks
            WHERE portfolio_id=:portfolio_id
            ORDER BY document_order
        """),
        {"portfolio_id": portfolio_id},
    ).mappings().all()
    return [dict(row) for row in rows]
