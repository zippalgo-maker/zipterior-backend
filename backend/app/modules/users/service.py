from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.modules.audit.service import AuditService
from app.modules.users import repository


class WrongPasswordError(Exception):
    pass


def withdraw_self(session: Session, user: dict[str, Any], *, password: str, reason: str | None) -> dict[str, Any]:
    stored_hash = repository.find_password_hash(session, user["id"])
    if not stored_hash or not verify_password(password, stored_hash):
        raise WrongPasswordError("비밀번호가 일치하지 않습니다.")

    owned_company = repository.find_owned_company(session, user["id"]) if user["role"] == "company" else None

    try:
        repository.withdraw_user(session, user["id"])
        repository.revoke_all_refresh_tokens(session, user["id"], "user_self_withdrawn")
        AuditService.record(
            session=session,
            admin_user_id=None,
            action_type="user.self_withdrawn",
            target_type="user",
            target_id=user["id"],
            before_data={"user_status": user["status"]},
            after_data={"user_status": "withdrawn"},
            reason=reason or "회원 본인 탈퇴",
            metadata={"source": "public_api"},
        )

        if owned_company is not None:
            repository.withdraw_company(session, owned_company["id"])
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="company.self_withdrawn",
                target_type="company",
                target_id=owned_company["id"],
                before_data={"company_status": owned_company["status"]},
                after_data={"company_status": "inactive"},
                reason=reason or "대표 회원 탈퇴로 인한 업체 탈퇴",
                metadata={"source": "public_api"},
            )

        session.commit()
    except Exception:
        session.rollback()
        raise

    return {"withdrawn": True, "message": "탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다."}
