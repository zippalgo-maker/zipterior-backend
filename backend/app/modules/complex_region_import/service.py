from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.complex_region_import import repository


class ComplexRegionImportNotFoundError(ValueError):
    pass


class ComplexRegionImportStateError(ValueError):
    pass


_TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed", "cancelled"}


class ComplexRegionImportService:
    @staticmethod
    def create_job(session: Session, *, admin_user_id: int, sigungu_query: str) -> dict[str, Any]:
        job_id = repository.create_job(
            session, requested_by=admin_user_id, sigungu_query=sigungu_query.strip()
        )
        session.commit()
        return repository.get_job(session, job_id=job_id)

    @staticmethod
    def create_cross_check_job(
        session: Session, *, admin_user_id: int, sigungu_query: str
    ) -> dict[str, Any]:
        """v2.5.1(2026-08-22): 법정동 훑기(sweep)와 별개로, 네이버 통합검색
        으로 같은 시군구를 한 번 더 조회해 우리 DB에 없는 단지가 있는지
        대조하는 이중검사 job. V2.5.0_PLAN.md 참고."""
        job_id = repository.create_job(
            session,
            requested_by=admin_user_id,
            sigungu_query=sigungu_query.strip(),
            job_kind="cross_check",
        )
        session.commit()
        return repository.get_job(session, job_id=job_id)

    @staticmethod
    def retry_failed_dongs(
        session: Session, *, admin_user_id: int, job_id: int
    ) -> dict[str, Any]:
        """2026-08-22: 원래 job에서 status='failed'로 남은 법정동만 골라
        새 sweep job을 만든다. 실패 원인이 전부 네이버 abuse 차단(HTTP
        307)이었음을 실측으로 확인했고(고양시 job #16), 시간이 지난 뒤
        같은 법정동을 다시 돌리면 대부분 해결된다(과거 양평군 사례와
        동일한 패턴). 정부 법정동코드 API는 다시 안 부른다 -- 원래
        job의 summary.dong_results에 이미 검증된 code가 있다."""
        job = ComplexRegionImportService.get_job(session, job_id=job_id)
        summary = job.get("summary") or {}
        failed_entries = [
            {"code": d["code"], "name": d["name"], "dong_name": d["dong_name"]}
            for d in (summary.get("dong_results") or [])
            if d.get("status") == "failed"
        ]
        if not failed_entries:
            raise ComplexRegionImportStateError(
                "재시도할 실패 법정동이 없습니다."
            )
        new_job_id = repository.create_job(
            session,
            requested_by=admin_user_id,
            sigungu_query=job["sigungu_query"],
            job_kind="sweep",
            dong_codes_filter=failed_entries,
        )
        # 2026-08-22: 원래 job에 재시도 job id를 남겨서, 프론트가 원래
        # job 상세를 다시 열었을 때 "재시도" 버튼 대신 "이미 재시도함"
        # 안내로 바꿀 수 있게 한다(실제로 사용자가 버튼을 계속 눌러
        # 중복 job이 쌓이는 문제가 있었음).
        repository.mark_job_retried(session, job_id=job_id, retry_job_id=new_job_id)
        session.commit()
        return repository.get_job(session, job_id=new_job_id)

    @staticmethod
    def list_jobs(session: Session, *, limit: int) -> list[dict[str, Any]]:
        return repository.list_jobs(session, limit=limit)

    @staticmethod
    def list_sigungu_options(session: Session) -> list[dict[str, Any]]:
        return repository.list_sigungu_options(session)

    @staticmethod
    def get_job(session: Session, *, job_id: int) -> dict[str, Any]:
        job = repository.get_job(session, job_id=job_id)
        if job is None:
            raise ComplexRegionImportNotFoundError("작업을 찾을 수 없습니다.")
        return job

    @staticmethod
    def cancel_job(session: Session, *, job_id: int) -> dict[str, Any]:
        job = ComplexRegionImportService.get_job(session, job_id=job_id)
        if job["status"] in _TERMINAL_STATUSES:
            raise ComplexRegionImportStateError("이미 종료된 작업입니다.")
        repository.update_job(session, job_id=job_id, changes={"status": "cancelled"})
        session.execute(
            text(
                "UPDATE complex_region_import_jobs SET completed_at=NOW() "
                "WHERE id=:job_id"
            ),
            {"job_id": job_id},
        )
        session.commit()
        return repository.get_job(session, job_id=job_id)
