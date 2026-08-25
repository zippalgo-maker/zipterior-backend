import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_admin_action_log(
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
    query = text(
        """
        INSERT INTO admin_action_logs (
            admin_user_id,
            action_type,
            target_type,
            target_id,
            before_data,
            after_data,
            reason,
            request_id,
            ip_address,
            user_agent,
            metadata
        )
        VALUES (
            :admin_user_id,
            :action_type,
            :target_type,
            :target_id,
            CAST(:before_data AS jsonb),
            CAST(:after_data AS jsonb),
            :reason,
            :request_id,
            CAST(:ip_address AS inet),
            :user_agent,
            CAST(:metadata AS jsonb)
        )
        RETURNING id
        """
    )

    result = session.execute(
        query,
        {
            "admin_user_id": admin_user_id,
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "before_data": json.dumps(
                before_data or {},
                ensure_ascii=False,
            ),
            "after_data": json.dumps(
                after_data or {},
                ensure_ascii=False,
            ),
            "reason": reason,
            "request_id": request_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": json.dumps(
                metadata or {},
                ensure_ascii=False,
            ),
        },
    )

    return int(result.scalar_one())
