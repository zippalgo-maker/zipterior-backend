"""2026-08-26: 기간을 정해 정지한 회원/업체가 그 기간이 지나면 자동으로
다시 이용 가능 상태가 되게 하는 백그라운드 워커. bulk_import worker와
같은 패턴(단일 프로세스라 스레드 하나로 충분, DB 상태 기반이라
재기동해도 그냥 이어서 돈다)."""
import logging
import threading
import time

from app.core.database import SessionLocal
from app.modules.admin.service import reactivate_expired_suspensions

logger = logging.getLogger(__name__)

_worker_started = False
_worker_lock = threading.Lock()
_POLL_SECONDS = 60


def _worker_loop() -> None:
    while True:
        try:
            with SessionLocal() as session:
                result = reactivate_expired_suspensions(session)
            if result["companies"] or result["users"]:
                logger.info(
                    "만료된 이용정지 자동 해제: 업체 %d건, 회원 %d건",
                    result["companies"],
                    result["users"],
                )
        except Exception:
            logger.exception("이용정지 자동해제 worker 오류")
        time.sleep(_POLL_SECONDS)


def start_suspension_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop,
            name="zipterior-suspension-reactivation",
            daemon=True,
        )
        thread.start()
        _worker_started = True
