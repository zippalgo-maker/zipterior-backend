import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_event(
    session: Session,
    *,
    event_name: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    event_version: int = 1,
) -> UUID:
    query = text(
        """
        INSERT INTO event_outbox (
            event_name,
            event_version,
            aggregate_type,
            aggregate_id,
            payload,
            metadata
        )
        VALUES (
            :event_name,
            :event_version,
            :aggregate_type,
            :aggregate_id,
            CAST(:payload AS jsonb),
            CAST(:metadata AS jsonb)
        )
        RETURNING id
        """
    )

    result = session.execute(
        query,
        {
            "event_name": event_name,
            "event_version": event_version,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(
                payload or {},
                ensure_ascii=False,
            ),
            "metadata": json.dumps(
                metadata or {},
                ensure_ascii=False,
            ),
        },
    )

    return result.scalar_one()
