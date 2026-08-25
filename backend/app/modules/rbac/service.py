from sqlalchemy.orm import Session

from app.modules.rbac import repository


class PermissionService:
    @staticmethod
    def get_effective_permissions(
        session: Session,
        user_id: int,
    ) -> set[str]:
        role = repository.get_user_role(session, user_id)

        if role is None:
            return set()

        if role == "super_admin":
            permissions = repository.get_all_permissions(session)
        else:
            permissions = repository.get_role_permissions(
                session,
                user_id,
            )

        overrides = repository.get_permission_overrides(
            session,
            user_id,
        )

        for permission_key, effect in overrides.items():
            if effect == "allow":
                permissions.add(permission_key)
            elif effect == "deny":
                permissions.discard(permission_key)

        return permissions

    @classmethod
    def has_permission(
        cls,
        session: Session,
        user_id: int,
        permission_key: str,
    ) -> bool:
        return permission_key in cls.get_effective_permissions(
            session,
            user_id,
        )

    @classmethod
    def require_permission(
        cls,
        session: Session,
        user_id: int,
        permission_key: str,
    ) -> None:
        if not cls.has_permission(
            session,
            user_id,
            permission_key,
        ):
            raise PermissionError(
                f"권한이 필요합니다: {permission_key}"
            )
