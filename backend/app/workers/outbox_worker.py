#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.logging import configure_logging


logger = logging.getLogger("zipterior.outbox")


class OutboxMaintenanceWorker:
    """Conservative outbox maintenance.

    v0.6.3 intentionally does NOT mark pending events as completed because
    downstream consumers have not yet been defined. It safely recovers stale
    processing rows and exposes queue metrics. This prevents event loss while
    preparing production worker operations.
    """

    def __init__(self, *, stale_minutes: int = 15, max_attempts: int = 10):
        self.worker_id = f"outbox-maintenance-{uuid4()}"
        self.stale_minutes = max(1, stale_minutes)
        self.max_attempts = max(1, max_attempts)

    def run_once(self, *, apply: bool = True) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.stale_minutes)
        with SessionLocal() as session:
            counts = {
                row[0]: int(row[1])
                for row in session.execute(
                    text("SELECT status, COUNT(*) FROM event_outbox GROUP BY status")
                ).all()
            }

            stale = int(
                session.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM event_outbox
                        WHERE status='processing'
                          AND locked_at IS NOT NULL
                          AND locked_at < :cutoff
                    """),
                    {"cutoff": cutoff},
                ).scalar_one()
            )

            retryable_failed = int(
                session.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM event_outbox
                        WHERE status='failed'
                          AND attempt_count < :max_attempts
                          AND available_at <= NOW()
                    """),
                    {"max_attempts": self.max_attempts},
                ).scalar_one()
            )

            if apply:
                session.execute(
                    text("""
                        UPDATE event_outbox
                        SET status='pending',
                            locked_at=NULL,
                            locked_by=NULL,
                            updated_at=NOW(),
                            last_error=COALESCE(last_error, '') ||
                                CASE WHEN COALESCE(last_error, '')='' THEN '' ELSE E'\n' END ||
                                'Recovered stale processing lock by v0.6.3 maintenance worker'
                        WHERE status='processing'
                          AND locked_at IS NOT NULL
                          AND locked_at < :cutoff
                    """),
                    {"cutoff": cutoff},
                )
                session.execute(
                    text("""
                        UPDATE event_outbox
                        SET status='pending',
                            locked_at=NULL,
                            locked_by=NULL,
                            updated_at=NOW()
                        WHERE status='failed'
                          AND attempt_count < :max_attempts
                          AND available_at <= NOW()
                    """),
                    {"max_attempts": self.max_attempts},
                )
                session.commit()

        result = {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
            "stale_processing": stale,
            "retryable_failed": retryable_failed,
        }
        logger.info("outbox maintenance completed: %s", result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stale-minutes", type=int, default=15)
    parser.add_argument("--max-attempts", type=int, default=10)
    args = parser.parse_args()
    configure_logging()
    result = OutboxMaintenanceWorker(
        stale_minutes=args.stale_minutes,
        max_attempts=args.max_attempts,
    ).run_once(apply=not args.dry_run)
    print("OUTBOX_MAINTENANCE_OK", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
