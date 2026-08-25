import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


JOB_COLUMNS = (
    "id, requested_by, sigungu_query, job_kind, status, total_dong_count, "
    "processed_dong_count, total_count, processed_count, success_count, "
    "duplicate_count, failed_count, error_message, summary, dong_codes_filter, "
    "created_at, started_at, completed_at"
)


def create_job(
    session: Session,
    *,
    requested_by: int,
    sigungu_query: str,
    job_kind: str = "sweep",
    dong_codes_filter: list[dict[str, Any]] | None = None,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO complex_region_import_jobs
                    (requested_by, sigungu_query, job_kind, dong_codes_filter)
                VALUES
                    (:requested_by, :sigungu_query, :job_kind, CAST(:dong_codes_filter AS jsonb))
                RETURNING id
                """
            ),
            {
                "requested_by": requested_by,
                "sigungu_query": sigungu_query,
                "job_kind": job_kind,
                "dong_codes_filter": (
                    json.dumps(dong_codes_filter, ensure_ascii=False)
                    if dong_codes_filter is not None
                    else None
                ),
            },
        ).scalar_one()
    )


def get_job(session: Session, *, job_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(f"SELECT {JOB_COLUMNS} FROM complex_region_import_jobs WHERE id=:id"),
        {"id": job_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def list_jobs(session: Session, *, limit: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            f"SELECT {JOB_COLUMNS} FROM complex_region_import_jobs "
            "ORDER BY created_at DESC, id DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


_ALLOWED_UPDATE_FIELDS = {
    "status", "total_dong_count", "processed_dong_count", "total_count",
    "processed_count", "success_count", "duplicate_count", "failed_count",
    "error_message", "summary", "started_at", "completed_at",
}


def update_job(session: Session, *, job_id: int, changes: dict[str, Any]) -> None:
    values = {key: value for key, value in changes.items() if key in _ALLOWED_UPDATE_FIELDS}
    if not values:
        return
    assignments = []
    params: dict[str, Any] = {"job_id": job_id}
    for key, value in values.items():
        if key == "summary":
            assignments.append(f"{key}=CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            assignments.append(f"{key}=:{key}")
            params[key] = value
    assignments.append("updated_at=NOW()")
    session.execute(
        text(
            f"UPDATE complex_region_import_jobs SET {', '.join(assignments)} "
            "WHERE id=:job_id"
        ),
        params,
    )


def increment_job_counts(
    session: Session,
    *,
    job_id: int,
    processed_delta: int = 0,
    success_delta: int = 0,
    duplicate_delta: int = 0,
    failed_delta: int = 0,
) -> None:
    session.execute(
        text(
            """
            UPDATE complex_region_import_jobs
            SET processed_count = processed_count + :processed_delta,
                success_count = success_count + :success_delta,
                duplicate_count = duplicate_count + :duplicate_delta,
                failed_count = failed_count + :failed_delta,
                updated_at = NOW()
            WHERE id=:job_id
            """
        ),
        {
            "job_id": job_id,
            "processed_delta": processed_delta,
            "success_delta": success_delta,
            "duplicate_delta": duplicate_delta,
            "failed_delta": failed_delta,
        },
    )


def next_runnable_job(session: Session) -> dict[str, Any] | None:
    row = session.execute(
        text(
            f"""
            SELECT {JOB_COLUMNS}
            FROM complex_region_import_jobs
            WHERE status IN ('queued', 'running')
            ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, created_at, id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


def list_sigungu_options(session: Session) -> list[dict[str, Any]]:
    """v2.5.1: 시군구 자동수집 화면에서 자유 텍스트 입력 대신 체크박스로
    고르기 위한 목록(시/도별 그룹핑용 sido_name 포함). data.go.kr 법정동
    코드 전체를 한 번 받아 시드해 둔 `sigungu_regions` 참조 테이블을
    그대로 반환한다. V2.5.0_PLAN.md 참고.

    2026-08-22 추가: 시군구별로 "이미 자동수집을 돌려봤는지, 결과가
    깨끗한지"를 체크박스 화면에 색으로 보여달라는 요청 -- 각 시군구에
    대해 가장 최근에 끝난 job을 찾아 상태를 같이 돌려준다.
    `sigungu_query`는 체크박스 화면에서 항상 `full_name`("경기도
    양평군")을 그대로 보내지만, 예전 자유 텍스트 시절 job(예: "과천시")도
    같이 잡히도록 시/도 접두어를 뗀 값으로 매칭한다."""
    rows = session.execute(
        text(
            """
            WITH normalized_jobs AS (
                SELECT
                    id, status, total_dong_count, failed_count, summary, completed_at, created_at,
                    regexp_replace(
                        sigungu_query,
                        '^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|'
                        '세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|'
                        '전라북도|전라남도|경상북도|경상남도|제주특별자치도)\\s*',
                        ''
                    ) AS bare_sigungu
                FROM complex_region_import_jobs
                WHERE status IN ('completed', 'completed_with_errors', 'failed')
            ),
            latest_jobs AS (
                SELECT DISTINCT ON (bare_sigungu) *
                FROM normalized_jobs
                ORDER BY bare_sigungu, created_at DESC
            )
            SELECT
                sr.code, sr.sido_name, sr.sigungu_name, sr.full_name,
                lj.id AS latest_job_id,
                lj.status AS latest_job_status,
                lj.total_dong_count AS latest_total_dong_count,
                COALESCE((lj.summary->>'failed_dong_count')::int, 0) AS latest_failed_dong_count,
                lj.summary->'failed_dong_names' AS latest_failed_dong_names,
                lj.completed_at AS latest_completed_at
            FROM sigungu_regions sr
            LEFT JOIN latest_jobs lj ON lj.bare_sigungu = sr.sigungu_name
            ORDER BY sr.sido_name, sr.full_name
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def mark_job_retried(session: Session, *, job_id: int, retry_job_id: int) -> None:
    """2026-08-22: "실패한 법정동만 재시도" 실행 시 원래 job의 summary에
    새로 만든 재시도 job의 id를 남긴다. 원래 job의 dong_results는 그
    job이 실행되던 시점에 얼어붙은 데이터라, 재시도가 나중에 성공해도
    저절로 안 바뀐다 -- 그래서 그 job 상세를 다시 열었을 때 "재시도"
    버튼을 계속 보여주는 대신 이 필드로 "이미 재시도했다"를 판단해
    안내로 바꾼다(admin-api.js criJobDetailHtml 참고)."""
    session.execute(
        text(
            """
            UPDATE complex_region_import_jobs
            SET summary = COALESCE(summary, '{}'::jsonb)
                || jsonb_build_object('retry_job_id', :retry_job_id),
                updated_at = NOW()
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id, "retry_job_id": retry_job_id},
    )


def is_cancelled(session: Session, *, job_id: int) -> bool:
    status = session.execute(
        text("SELECT status FROM complex_region_import_jobs WHERE id=:id"),
        {"id": job_id},
    ).scalar_one_or_none()
    return status == "cancelled"
