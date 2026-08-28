"""라우터가 부르는 비즈니스 로직. 권한 위반은 HTTPException으로 바로
올린다(다른 관리자 모듈들도 이 정도 규모에서는 별도 예외 클래스 없이
서비스 계층에서 바로 HTTPException을 쓴다 -- bulk_import처럼 상태머신이
복잡한 모듈만 전용 예외를 둔다)."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.chat import permissions, repository
from app.modules.chat.constants import DEFAULT_MESSAGE_PAGE_SIZE


def _summary_from_room_row(row: dict[str, Any]) -> dict[str, Any]:
    customer_name = row.get("customer_name")
    last = None
    if row.get("last_id") is not None:
        last = {
            "id": row["last_id"],
            "content": row["last_content"],
            "message_type": row["last_message_type"],
            "created_at": row["last_created_at"],
        }
    return {
        "id": row["id"],
        "channel": row["room_type"],
        "customerId": row.get("customer_id"),
        "customerName": customer_name or "고객",
        "requesterId": row.get("requester_user_id"),
        "requesterName": customer_name or "회원",
        "requesterRole": "company" if row["room_type"] == "support" and row.get("requester_role") == "company" else "customer",
        "companyId": row.get("company_id"),
        "companyName": row.get("company_name") or "고객센터",
        "companyPhone": row.get("company_phone") or "",
        "status": row["status"],
        "supportActive": row["status"] == "active",
        "updatedAt": row.get("last_message_at") or row["created_at"],
        "lastMessage": last,
    }


def _message_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sender": row["sender_role"],
        "type": row["message_type"],
        "text": row["content"] or "",
        "portfolioId": row["portfolio_id"],
        "image": row["file_path"] or "",
        "thumbnail": row["thumbnail_path"] or "",
        "mimeType": row["mime_type"],
        "fileSize": row["file_size_bytes"],
        "createdAt": row["created_at"],
    }


def get_room_or_404(session: Session, room_id: int) -> dict[str, Any]:
    room = repository.find_room(session, room_id)
    if not room:
        raise HTTPException(404, "채팅방을 찾을 수 없습니다.")
    return room


def require_access(session: Session, user: dict, room: dict) -> None:
    if not permissions.can_access_room(session, user, room):
        raise HTTPException(403, "채팅방 접근 권한이 없습니다.")


def require_send_allowed(user: dict, room: dict) -> None:
    if not permissions.can_send_in_room(user, room):
        raise HTTPException(403, "관리자는 업체 채팅을 모니터링만 할 수 있습니다.")


def serialize_room(session: Session, room_id: int) -> dict[str, Any]:
    row = repository.find_room_summary(session, room_id)
    if not row:
        raise HTTPException(404, "채팅방을 찾을 수 없습니다.")
    return _summary_from_room_row(row)


def list_rooms(session: Session, user: dict) -> dict[str, Any]:
    role = user["role"]
    if role in ("admin", "super_admin"):
        rows = repository.list_rooms_for_admin(session)
    elif role == "customer":
        rows = repository.list_rooms_for_customer(session, user_id=user["id"])
    elif role == "company":
        company_id = permissions.company_id_for_user(session, user)
        rows = repository.list_rooms_for_company(session, user_id=user["id"], company_id=company_id)
    else:
        rows = []
    return {"items": [_summary_from_room_row(row) for row in rows]}


def open_company_room(session: Session, user: dict, *, company_id: int, portfolio_id: int | None) -> dict[str, Any]:
    if user["role"] != "customer":
        raise HTTPException(403, "일반회원만 업체 상담을 시작할 수 있습니다.")
    if not repository.company_exists(session, company_id):
        raise HTTPException(404, "업체를 찾을 수 없습니다.")

    room = repository.find_active_company_room(session, customer_id=user["id"], company_id=company_id)
    if not room:
        room_id = repository.create_company_room(
            session, customer_id=user["id"], company_id=company_id, portfolio_id=portfolio_id
        )
        session.commit()
    else:
        room_id = room["id"]
    return serialize_room(session, room_id)


def open_support_room(session: Session, user: dict) -> dict[str, Any]:
    room = repository.find_active_support_room(session, requester_user_id=user["id"])
    if not room:
        room_id = repository.create_support_room(session, requester_user_id=user["id"], requester_role=user["role"])
        session.commit()
    else:
        room_id = room["id"]
    return serialize_room(session, room_id)


def list_messages(
    session: Session, user: dict, room_id: int, *, limit: int = DEFAULT_MESSAGE_PAGE_SIZE, before_id: int | None = None
) -> dict[str, Any]:
    room = get_room_or_404(session, room_id)
    require_access(session, user, room)
    rows, has_more = repository.list_messages_page(session, room_id=room_id, limit=limit, before_id=before_id)
    return {"items": [_message_item(row) for row in rows], "hasMore": has_more}


def send_text_message(session: Session, user: dict, room_id: int, *, content: str, portfolio_id: int | None) -> tuple[dict[str, Any], int]:
    room = get_room_or_404(session, room_id)
    require_access(session, user, room)
    require_send_allowed(user, room)
    message_id = repository.insert_text_message(
        session, room_id=room_id, sender_user_id=user["id"], content=content.strip(), portfolio_id=portfolio_id
    )
    session.commit()
    return {"id": message_id, "room_id": room_id, "sent": True}, message_id


def save_attachment_message(
    session: Session, user: dict, room_id: int, *, url: str, mime_type: str, file_size_bytes: int
) -> tuple[dict[str, Any], int]:
    room = get_room_or_404(session, room_id)
    require_access(session, user, room)
    require_send_allowed(user, room)
    message_id = repository.insert_image_message(session, room_id=room_id, sender_user_id=user["id"])
    repository.insert_attachment(session, message_id=message_id, file_path=url, mime_type=mime_type, file_size_bytes=file_size_bytes)
    repository.touch_room_activity(session, room_id)
    return {
        "id": message_id,
        "room_id": room_id,
        "type": "image",
        "image": url,
        "mime_type": mime_type,
        "file_size_bytes": file_size_bytes,
    }, message_id


def mark_read(session: Session, user: dict, room_id: int) -> dict[str, Any]:
    room = repository.find_room(session, room_id)
    if not room or not permissions.can_access_room(session, user, room):
        raise HTTPException(403, "채팅방 접근 권한이 없습니다.")
    repository.mark_room_read(session, room_id=room_id, user_id=user["id"], role=user["role"])
    session.commit()
    return {"read": True}


def close_room(session: Session, user: dict, room_id: int) -> dict[str, Any]:
    room = repository.find_room(session, room_id)
    if not room or room["room_type"] != "support" or user["role"] not in ("admin", "super_admin"):
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    repository.close_support_room(session, room_id)
    session.commit()
    return {"closed": True}


def build_push_payload(session: Session, room_id: int, message_id: int) -> dict[str, Any] | None:
    row = repository.find_message_for_push(session, message_id)
    if not row:
        return None
    room = repository.find_room(session, room_id)
    if not room:
        return None
    return {
        "type": "chat_message",
        "roomId": room_id,
        "message": _message_item(row),
        "room": serialize_room(session, room_id),
        "recipients": repository.room_recipient_ids(session, room),
    }
