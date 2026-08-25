#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionLocal


REQUIRED_INDEXES = {
    "idx_event_outbox_pending",
    "idx_event_outbox_aggregate",
    "idx_view_events_portfolio_date",
}


def main() -> int:
    with SessionLocal() as session:
        indexes = {
            row[0]
            for row in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            ).all()
        }
        missing = sorted(REQUIRED_INDEXES - indexes)
        outbox = session.execute(text("""
            SELECT status, COUNT(*)
            FROM event_outbox
            GROUP BY status
            ORDER BY status
        """)).all()
        connections = int(session.execute(text("SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database()")) .scalar_one())

    print(f"DB_REQUIRED_INDEX_MISSING={missing}")
    print(f"DB_CONNECTIONS={connections}")
    print("OUTBOX_COUNTS=" + ",".join(f"{status}:{count}" for status, count in outbox))
    if missing:
        return 1
    print("DB_HEALTH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
