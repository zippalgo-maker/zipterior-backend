from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.event_outbox import repository


class EventOutboxService:
    @staticmethod
    def publish(
        session: Session,
        *,
        event_name: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        event_version: int = 1,
    ) -> UUID:
        return repository.create_event(
            session=session,
            event_name=event_name,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            metadata=metadata,
            event_version=event_version,
        )
