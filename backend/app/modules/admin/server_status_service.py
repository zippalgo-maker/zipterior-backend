"""
2026-08-26: 관리자 대시보드 "서버 상태" 패널 -- 디스크 사용량 표시 +
안전 범위 내 정리 대상(파이썬 캐시 / 수정전 백업파일 / 옛 배포 릴리즈 /
완료된 일괄등록 원본파일) 조회·선택삭제.

주의: bulk_import의 원본(imports/{job_id})은 job이 완전히 끝나기
(completed / completed_with_errors / cancelled) 전에는 재시도용으로
필요할 수 있으므로 절대 삭제 후보로 노출하지 않는다 -- ALLOWED_DELETE_STATUSES
밖의 job은 화면에는 보여주되(blocked=True) 실제 삭제 요청이 와도 서버에서
한 번 더 막는다(방어적 이중 체크).
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.modules.audit.service import AuditService


class WrongPasswordError(Exception):
    """관리자 비밀번호 확인 실패 -- 정리 삭제 진행 전 재확인용."""

ZIPTERIOR_ROOT = Path("/srv/zipterior")
FRONTEND_ROOT = Path("/var/www/zipterior")
BACKEND_ROOT = ZIPTERIOR_ROOT / "backend"
IMPORTS_ROOT = ZIPTERIOR_ROOT / "imports"
RELEASES_ROOT = ZIPTERIOR_ROOT / "releases"

# 디스크 용량 표시 대상. 서버에 디스크가 추가되면 여기만 늘리면 됨.
DISK_MOUNTS = [
    ("/", "1번 디스크 (시스템/DB)"),
    ("/mnt/vdb_data", "2번 디스크 (업로드 저장소)"),
]

WARNING_PERCENT = 75.0
CRITICAL_PERCENT = 90.0

# .bak_* 스캔에서 절대 건드리지 않을 디렉터리(대용량/운영데이터/가상환경).
BAK_SCAN_ROOTS = [BACKEND_ROOT, FRONTEND_ROOT]
BAK_SCAN_EXCLUDE_DIRNAMES = {
    "venv", "__pycache__", ".git", "node_modules",
    "backups", "imports", "releases", "media", "logs",
    "uploads",  # 실제 업로드 이미지(수십만~백만 파일) -- 절대 순회하면 안 됨
}

# imports/{job_id} 원본을 지워도 되는(=더 이상 재시도에 안 쓰는) job 상태.
ALLOWED_DELETE_STATUSES = {"completed", "completed_with_errors", "cancelled"}


def _disk_level(used_percent: float) -> str:
    if used_percent >= CRITICAL_PERCENT:
        return "critical"
    if used_percent >= WARNING_PERCENT:
        return "warning"
    return "ok"


def _disk_usage_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for mount, label in DISK_MOUNTS:
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        # usage.used(=shutil.disk_usage 기본값)는 os.statvfs의 f_bfree 기준이라
        # ext4 root 예약공간(기본 5%)을 "안 쓴 것"으로 잘못 계산해 실제보다 적게
        # 나온다(예: 2번 디스크가 root 예약 5GB 때문에 진짜 여유 0B인데도 94.9%로
        # 표시됨). free_bytes(f_bavail 기준, 일반 유저가 실제 쓸 수 있는 여유)와
        # 같은 기준으로 계산해 화면의 퍼센트/여유용량이 서로 어긋나지 않게 한다.
        used_percent = round((usage.total - usage.free) / usage.total * 100, 1) if usage.total else 0.0
        items.append({
            "mount": mount,
            "label": label,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": used_percent,
            "level": _disk_level(used_percent),
        })
    return items


def _dir_size(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _pycache_candidate() -> dict[str, Any] | None:
    total = 0
    latest_mtime: float | None = None
    for dirpath, dirnames, _filenames in os.walk(BACKEND_ROOT):
        if "venv" in dirpath.split(os.sep):
            dirnames[:] = []
            continue
        if "__pycache__" in dirnames:
            cache_dir = Path(dirpath) / "__pycache__"
            total += _dir_size(cache_dir)
            try:
                mtime = cache_dir.stat().st_mtime
                latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)
            except OSError:
                pass
    if total == 0:
        return None
    return {
        "id": "pycache",
        "type": "pycache",
        "label": "파이썬 캐시 전체(__pycache__)",
        "size_bytes": total,
        "modified_at": (
            datetime.fromtimestamp(latest_mtime, tz=timezone.utc) if latest_mtime else None
        ),
        "blocked": False,
        "blocked_reason": None,
        "_paths": None,  # 삭제 시 위 로직을 다시 돌려서 지움(경로 목록을 여기 담지 않음)
    }


def _bak_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for root in BAK_SCAN_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in BAK_SCAN_EXCLUDE_DIRNAMES]
            for name in filenames:
                if ".bak" not in name:
                    continue
                fp = Path(dirpath) / name
                try:
                    stat = fp.stat()
                except OSError:
                    continue
                rel = fp.resolve().as_posix()
                candidates.append({
                    "id": f"bak:{rel}",
                    "type": "bak_file",
                    "label": fp.relative_to(root.parent).as_posix(),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    "blocked": False,
                    "blocked_reason": None,
                    "_path": rel,
                })
    candidates.sort(key=lambda c: c["modified_at"])
    return candidates


def _release_candidates() -> list[dict[str, Any]]:
    if not RELEASES_ROOT.exists():
        return []
    entries = []
    for child in RELEASES_ROOT.iterdir():
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        entries.append((child, mtime))
    entries.sort(key=lambda pair: pair[1])
    candidates = []
    for idx, (child, mtime) in enumerate(entries):
        is_latest = idx == len(entries) - 1
        candidates.append({
            "id": f"release:{child.resolve().as_posix()}",
            "type": "release",
            "label": f"releases/{child.name}",
            "size_bytes": _dir_size(child),
            "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc),
            "blocked": is_latest,
            "blocked_reason": "가장 최근 배포 스냅샷은 보호됩니다." if is_latest else None,
            "_path": child.resolve().as_posix(),
        })
    return candidates


def _import_job_candidates(session: Session) -> list[dict[str, Any]]:
    if not IMPORTS_ROOT.exists():
        return []
    job_dirs = [
        child for child in IMPORTS_ROOT.iterdir()
        if child.is_dir() and child.name.isdigit()
    ]
    if not job_dirs:
        return []
    job_ids = [int(child.name) for child in job_dirs]
    rows = session.execute(
        text("""
            SELECT id, status, original_filename, failed_count
            FROM bulk_import_jobs
            WHERE id = ANY(:ids)
        """),
        {"ids": job_ids},
    ).mappings().all()
    status_by_id = {int(row["id"]): row for row in rows}

    candidates = []
    for child in job_dirs:
        job_id = int(child.name)
        job = status_by_id.get(job_id)
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if job is None:
            # DB에 job 기록이 없는 원본(수동 임포트 등) -- 안전하게 항상 막아둠.
            blocked, reason = True, "연결된 일괄등록 기록을 찾을 수 없어 보호합니다."
        elif job["status"] not in ALLOWED_DELETE_STATUSES:
            blocked, reason = True, f"job #{job_id} 상태가 '{job['status']}'라 재시도용으로 필요할 수 있습니다."
        elif int(job["failed_count"] or 0) > 0:
            blocked, reason = True, f"job #{job_id}에 실패건 {job['failed_count']}건이 남아있어 재시도용으로 보호합니다."
        else:
            blocked, reason = False, None
        label = f"imports/{job_id}"
        if job is not None and job.get("original_filename"):
            label += f" ({job['original_filename']})"
        candidates.append({
            "id": f"import_job:{job_id}",
            "type": "import_job",
            "label": label,
            "size_bytes": _dir_size(child),
            "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc),
            "blocked": blocked,
            "blocked_reason": reason,
            "_path": child.resolve().as_posix(),
            "_job_id": job_id,
        })
    candidates.sort(key=lambda c: c["modified_at"])
    return candidates


def _db_stats(session: Session) -> dict[str, int]:
    row = session.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND role='customer') AS customer_members,
          (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND role='company') AS company_members,
          (SELECT COUNT(*) FROM companies WHERE deleted_at IS NULL) AS companies,
          (SELECT COUNT(*) FROM portfolios WHERE deleted_at IS NULL) AS portfolios,
          (SELECT COUNT(*) FROM portfolio_images) AS portfolio_images
    """)).mappings().one()
    return {k: int(v or 0) for k, v in row.items()}


def _cleanup_history(session: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT
          l.id,
          COALESCE(u.name, u.email::text, 'admin#'||l.admin_user_id::text) AS admin_label,
          l.reason,
          l.before_data,
          l.after_data,
          l.created_at
        FROM admin_action_logs l
        LEFT JOIN users u ON u.id = l.admin_user_id
        WHERE l.action_type = 'server.cleanup'
        ORDER BY l.created_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    history = []
    for row in rows:
        before = row["before_data"] or {}
        after = row["after_data"] or {}
        history.append({
            "id": int(row["id"]),
            "admin_label": row["admin_label"],
            "reason": row["reason"],
            "deleted": before.get("deleted") or [],
            "skipped": before.get("skipped") or [],
            "freed_bytes": int(after.get("freed_bytes") or 0),
            "created_at": row["created_at"],
        })
    return history


def get_status(session: Session) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    pycache = _pycache_candidate()
    if pycache:
        candidates.append(pycache)
    candidates.extend(_bak_candidates())
    candidates.extend(_release_candidates())
    candidates.extend(_import_job_candidates(session))

    cleanup_total = sum(c["size_bytes"] for c in candidates if not c["blocked"])

    return {
        "disks": _disk_usage_items(),
        "db_stats": _db_stats(session),
        "cleanup_candidates": [
            {k: v for k, v in c.items() if not k.startswith("_")}
            for c in candidates
        ],
        "cleanup_total_bytes": cleanup_total,
        "cleanup_history": _cleanup_history(session),
        "checked_at": datetime.now(tz=timezone.utc),
    }


def _resolve_candidate(session: Session, candidate_id: str) -> dict[str, Any] | None:
    """target id 하나를 다시 계산해서(클라이언트가 보낸 크기/차단여부를 신뢰하지
    않고) 최신 상태로 재검증한다."""
    if candidate_id == "pycache":
        return _pycache_candidate()
    if candidate_id.startswith("bak:"):
        for c in _bak_candidates():
            if c["id"] == candidate_id:
                return c
        return None
    if candidate_id.startswith("release:"):
        for c in _release_candidates():
            if c["id"] == candidate_id:
                return c
        return None
    if candidate_id.startswith("import_job:"):
        for c in _import_job_candidates(session):
            if c["id"] == candidate_id:
                return c
        return None
    return None


def _delete_candidate(candidate: dict[str, Any]) -> int:
    ctype = candidate["type"]
    size = candidate["size_bytes"]
    if ctype == "pycache":
        for dirpath, dirnames, _filenames in os.walk(BACKEND_ROOT):
            if "venv" in dirpath.split(os.sep):
                dirnames[:] = []
                continue
            if "__pycache__" in dirnames:
                shutil.rmtree(Path(dirpath) / "__pycache__", ignore_errors=True)
        return size
    path = Path(candidate["_path"])
    # 안전장치: 허용된 루트 밖은 절대 건드리지 않음.
    allowed_roots = [BACKEND_ROOT, FRONTEND_ROOT, RELEASES_ROOT, IMPORTS_ROOT]
    if not any(path == root or root in path.parents for root in allowed_roots):
        raise ValueError(f"허용되지 않은 경로: {path}")
    if ctype == "bak_file":
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)
    return size


def _verify_admin_password(session: Session, *, admin_user_id: int, password: str) -> bool:
    row = session.execute(
        text("SELECT password_hash FROM users WHERE id = :id"),
        {"id": admin_user_id},
    ).mappings().one_or_none()
    if row is None or not row["password_hash"]:
        return False
    return verify_password(password, row["password_hash"])


def cleanup(
    session: Session,
    *,
    targets: list[str],
    admin_user_id: int,
    reason: str,
    password: str,
) -> dict[str, Any]:
    if not _verify_admin_password(session, admin_user_id=admin_user_id, password=password):
        raise WrongPasswordError("비밀번호가 일치하지 않습니다.")

    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for target_id in dict.fromkeys(targets):  # 중복 제거, 순서 유지
        candidate = _resolve_candidate(session, target_id)
        if candidate is None:
            skipped.append({"id": target_id, "reason": "대상을 찾을 수 없습니다(이미 삭제되었을 수 있음)."})
            continue
        if candidate["blocked"]:
            skipped.append({"id": target_id, "reason": candidate["blocked_reason"] or "삭제할 수 없는 대상입니다."})
            continue
        try:
            freed = _delete_candidate(candidate)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"id": target_id, "reason": f"삭제 실패: {exc}"})
            continue
        deleted.append({"id": target_id, "label": candidate["label"], "freed_bytes": freed})

    freed_total = sum(item["freed_bytes"] for item in deleted)

    AuditService.record(
        session=session,
        admin_user_id=admin_user_id,
        action_type="server.cleanup",
        target_type="server_maintenance",
        target_id=None,
        before_data={
            "deleted": deleted,
            "skipped": skipped,
        },
        after_data={"freed_bytes": freed_total},
        reason=reason,
    )
    session.commit()

    message = f"{len(deleted)}건 삭제, {round(freed_total / 1024 / 1024, 1)}MB 확보했습니다."
    if skipped:
        message += f" ({len(skipped)}건은 보호 대상이라 건너뜀)"

    return {
        "deleted": deleted,
        "skipped": skipped,
        "freed_bytes": freed_total,
        "message": message,
    }
