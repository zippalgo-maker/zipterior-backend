from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_role(session: Session, user_id: int) -> str | None:
    query = text(
        """
        SELECT role
        FROM users
        WHERE id = :user_id
          AND deleted_at IS NULL
        """
    )
    return session.execute(query, {"user_id": user_id}).scalar_one_or_none()


def get_role_permissions(session: Session, user_id: int) -> set[str]:
    query = text(
        """
        SELECT DISTINCT p.permission_key
        FROM user_admin_roles AS ur
        JOIN admin_role_permissions AS rp
          ON rp.role_id = ur.role_id
        JOIN admin_permissions AS p
          ON p.id = rp.permission_id
        WHERE ur.user_id = :user_id
        """
    )
    return set(session.execute(query, {"user_id": user_id}).scalars())


def get_permission_overrides(
    session: Session,
    user_id: int,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)

    query = text(
        """
        SELECT
            p.permission_key,
            o.effect
        FROM user_permission_overrides AS o
        JOIN admin_permissions AS p
          ON p.id = o.permission_id
        WHERE o.user_id = :user_id
          AND o.is_active = TRUE
          AND o.starts_at <= :now
          AND (
              o.ends_at IS NULL
              OR o.ends_at > :now
          )
        """
    )

    rows = session.execute(
        query,
        {"user_id": user_id, "now": now},
    ).mappings()

    return {
        row["permission_key"]: row["effect"]
        for row in rows
    }


def get_all_permissions(session: Session) -> set[str]:
    query = text(
        """
        SELECT permission_key
        FROM admin_permissions
        """
    )
    return set(session.execute(query).scalars())
