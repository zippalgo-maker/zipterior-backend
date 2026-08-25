from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.audit import repository


class AuditService:
    @staticmethod
    def record(
        session: Session,
        *,
        admin_user_id: int | None,
        action_type: str,
        target_type: str | None = None,
        target_id: int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        return repository.create_admin_action_log(
            session=session,
            admin_user_id=admin_user_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )
