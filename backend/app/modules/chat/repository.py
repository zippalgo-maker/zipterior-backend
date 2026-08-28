"""채팅 관련 DB 접근만 모아둔 계층. 여기 함수들은 권한 판단(permissions.py)
이나 HTTP 응답 형식은 모르고, 오직 SQL 실행 + 파이썬 dict 변환만 한다."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_room(session: Session, room_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text("SELECT * FROM chat_rooms WHERE id=:id"), {"id": room_id}
    ).mappings().one_or_none()
    return dict(row) if row else None


def company_exists(session: Session, company_id: int) -> bool:
    return session.execute(
        text("SELECT 1 FROM companies WHERE id=:c AND deleted_at IS NULL"), {"c": company_id}
    ).first() is not None


def find_active_company_room(session: Session, *, customer_id: int, company_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT * FROM chat_rooms
            WHERE room_type='company' AND customer_id=:u AND company_id=:c AND status<>'blocked'
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"u": customer_id, "c": company_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def create_company_room(session: Session, *, customer_id: int, company_id: int, portfolio_id: int | None) -> int:
    room_id = session.execute(
        text(
            """
            INSERT INTO chat_rooms(room_type,customer_id,company_id,requester_user_id,portfolio_id,status)
            VALUES('company',:u,:c,:u,:p,'active') RETURNING id
            """
        ),
        {"u": customer_id, "c": company_id, "p": portfolio_id},
    ).scalar_one()
    session.execute(
        text(
            "INSERT INTO chat_room_members(chat_room_id,user_id,member_role) VALUES(:r,:u,'customer') ON CONFLICT DO NOTHING"
        ),
        {"r": room_id, "u": customer_id},
    )
    return room_id


def find_active_support_room(session: Session, *, requester_user_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT * FROM chat_rooms
            WHERE room_type='support' AND requester_user_id=:u AND status<>'blocked'
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"u": requester_user_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def create_support_room(session: Session, *, requester_user_id: int, requester_role: str) -> int:
    room_id = session.execute(
        text(
            """
            INSERT INTO chat_rooms(room_type,customer_id,requester_user_id,status)
            VALUES('support',:cust,:u,'active') RETURNING id
            """
        ),
        {"cust": requester_user_id if requester_role == "customer" else None, "u": requester_user_id},
    ).scalar_one()
    session.execute(
        text(
            "INSERT INTO chat_room_members(chat_room_id,user_id,member_role) VALUES(:r,:u,:role) ON CONFLICT DO NOTHING"
        ),
        {"r": room_id, "u": requester_user_id, "role": requester_role},
    )
    return room_id


# ---- 방 목록(room summary) ----
# 2026-08-26: 방 개수만큼 이름/마지막메시지/업체정보를 재조회하던 N+1을
# 조인 1방으로 통합. rooms_for_*() 각각은 role별 WHERE절만 다르게 이
# 셀렉트를 공유한다.
_ROOM_LIST_SELECT = """
    SELECT
      r.id, r.room_type, r.customer_id, r.company_id, r.requester_user_id,
      r.status, r.created_at, r.last_message_at,
      cu.name AS customer_name,
      ru.role AS requester_role,
      co.name AS company_name, co.phone AS company_phone,
      lm.id AS last_id, lm.content AS last_content,
      lm.message_type AS last_message_type, lm.created_at AS last_created_at
    FROM chat_rooms r
    LEFT JOIN users cu ON cu.id = COALESCE(r.customer_id, r.requester_user_id)
    LEFT JOIN users ru ON ru.id = r.requester_user_id
    LEFT JOIN companies co ON co.id = r.company_id
    LEFT JOIN LATERAL (
        SELECT id, content, message_type, created_at
        FROM chat_messages m
        WHERE m.chat_room_id = r.id AND m.deleted_at IS NULL
        ORDER BY m.id DESC LIMIT 1
    ) lm ON true
"""


def list_rooms_for_admin(session: Session) -> list[dict[str, Any]]:
    # 2026-08-26: "채팅 모니터링"용 회원↔업체(company) 대화도 같이 내려줘야
    # 프론트(portal.js sortedChats('company'))가 목록을 채울 수 있다 --
    # support만 내려주고 있어서 모니터링 화면이 계속 비어 있던 버그.
    rows = session.execute(
        text(_ROOM_LIST_SELECT + " WHERE r.room_type IN ('support','company') ORDER BY COALESCE(r.last_message_at,r.created_at) DESC")
    ).mappings().all()
    return [dict(row) for row in rows]


def list_rooms_for_customer(session: Session, *, user_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            _ROOM_LIST_SELECT
            + " WHERE (r.customer_id=:u OR (r.room_type='support' AND r.requester_user_id=:u))"
              " ORDER BY COALESCE(r.last_message_at,r.created_at) DESC"
        ),
        {"u": user_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_rooms_for_company(session: Session, *, user_id: int, company_id: int | None) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            _ROOM_LIST_SELECT
            + " WHERE ((r.room_type='company' AND r.company_id=:c) OR (r.room_type='support' AND r.requester_user_id=:u))"
              " ORDER BY COALESCE(r.last_message_at,r.created_at) DESC"
        ),
        {"c": company_id, "u": user_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def find_room_summary(session: Session, room_id: int) -> dict[str, Any] | None:
    """단일 방 하나짜리 목록용 셀렉트(생성 직후 응답 등)."""
    row = session.execute(
        text(_ROOM_LIST_SELECT + " WHERE r.id=:id"), {"id": room_id}
    ).mappings().one_or_none()
    return dict(row) if row else None


# ---- 메시지 ----
_MESSAGE_SELECT = """
    SELECT m.id,m.sender_user_id,u.role AS sender_role,m.message_type,m.content,m.portfolio_id,m.created_at,
           a.file_path,a.thumbnail_path,a.mime_type,a.file_size_bytes
    FROM chat_messages m
    JOIN users u ON u.id=m.sender_user_id
    LEFT JOIN chat_attachments a ON a.message_id=m.id
    WHERE m.chat_room_id=:r AND m.deleted_at IS NULL
"""


def list_messages_page(
    session: Session, *, room_id: int, limit: int, before_id: int | None
) -> tuple[list[dict[str, Any]], bool]:
    """최신순으로 limit개를 가져온 뒤 시간순으로 뒤집어 반환한다.
    has_more는 그보다 오래된 메시지가 더 있는지."""
    query = _MESSAGE_SELECT
    params: dict[str, Any] = {"r": room_id, "limit": limit}
    if before_id is not None:
        query += " AND m.id<:before_id"
        params["before_id"] = before_id
    query += " ORDER BY m.id DESC LIMIT :limit"
    rows = [dict(row) for row in session.execute(text(query), params).mappings().all()]
    rows.reverse()
    has_more = False
    if rows and len(rows) == limit:
        has_more = session.execute(
            text(
                "SELECT 1 FROM chat_messages WHERE chat_room_id=:r AND deleted_at IS NULL AND id<:min_id LIMIT 1"
            ),
            {"r": room_id, "min_id": rows[0]["id"]},
        ).first() is not None
    return rows, has_more


def find_message_for_push(session: Session, message_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT m.id,m.sender_user_id,u.role AS sender_role,m.message_type,m.content,m.portfolio_id,m.created_at,
                   a.file_path,a.thumbnail_path,a.mime_type,a.file_size_bytes
            FROM chat_messages m
            JOIN users u ON u.id=m.sender_user_id
            LEFT JOIN chat_attachments a ON a.message_id=m.id
            WHERE m.id=:id
            """
        ),
        {"id": message_id},
    ).mappings().one_or_none()
    return dict(row) if row else None


def insert_text_message(session: Session, *, room_id: int, sender_user_id: int, content: str, portfolio_id: int | None) -> int:
    message_id = session.execute(
        text(
            "INSERT INTO chat_messages(chat_room_id,sender_user_id,message_type,content,portfolio_id) "
            "VALUES(:r,:u,'text',:c,:p) RETURNING id"
        ),
        {"r": room_id, "u": sender_user_id, "c": content, "p": portfolio_id},
    ).scalar_one()
    touch_room_activity(session, room_id)
    return message_id


def insert_image_message(session: Session, *, room_id: int, sender_user_id: int) -> int:
    return session.execute(
        text(
            "INSERT INTO chat_messages(chat_room_id,sender_user_id,message_type,content) "
            "VALUES(:r,:u,'image','') RETURNING id"
        ),
        {"r": room_id, "u": sender_user_id},
    ).scalar_one()


def insert_attachment(session: Session, *, message_id: int, file_path: str, mime_type: str, file_size_bytes: int) -> None:
    session.execute(
        text(
            "INSERT INTO chat_attachments(message_id,file_path,mime_type,file_size_bytes) VALUES(:m,:p,:t,:s)"
        ),
        {"m": message_id, "p": file_path, "t": mime_type, "s": file_size_bytes},
    )


def touch_room_activity(session: Session, room_id: int) -> None:
    session.execute(
        text("UPDATE chat_rooms SET last_message_at=now(),status='active',closed_at=NULL WHERE id=:r"),
        {"r": room_id},
    )


def mark_room_read(session: Session, *, room_id: int, user_id: int, role: str) -> None:
    last_id = session.execute(
        text("SELECT max(id) FROM chat_messages WHERE chat_room_id=:r"), {"r": room_id}
    ).scalar()
    session.execute(
        text(
            """
            INSERT INTO chat_room_members(chat_room_id,user_id,member_role,last_read_message_id)
            VALUES(:r,:u,:role,:m)
            ON CONFLICT(chat_room_id,user_id)
            DO UPDATE SET last_read_message_id=EXCLUDED.last_read_message_id, left_at=NULL
            """
        ),
        {"r": room_id, "u": user_id, "role": role, "m": last_id},
    )


def close_support_room(session: Session, room_id: int) -> None:
    session.execute(
        text("UPDATE chat_rooms SET status='closed',closed_at=now() WHERE id=:r"), {"r": room_id}
    )


# ---- 실시간 푸시 수신 대상 ----
def room_recipient_ids(session: Session, room: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    admin_ids = None
    if room["room_type"] == "company":
        if room.get("customer_id"):
            ids.add(room["customer_id"])
        company_id = room.get("company_id")
        if company_id:
            owner = session.execute(
                text("SELECT owner_user_id FROM companies WHERE id=:c"), {"c": company_id}
            ).scalar()
            if owner:
                ids.add(owner)
            ids.update(
                session.execute(
                    text("SELECT user_id FROM company_members WHERE company_id=:c AND status='active'"),
                    {"c": company_id},
                ).scalars().all()
            )
        # 2026-08-26: 관리자 "채팅 모니터링" 화면도 20초 폴링만 타지 말고
        # 실시간 푸시를 받도록(읽기 전용 참관자로 추가, 발신 권한과는 무관).
        admin_ids = admin_ids if admin_ids is not None else _admin_ids(session)
        ids.update(admin_ids)
    elif room["room_type"] == "support":
        if room.get("requester_user_id"):
            ids.add(room["requester_user_id"])
        admin_ids = admin_ids if admin_ids is not None else _admin_ids(session)
        ids.update(admin_ids)
    return ids


def _admin_ids(session: Session) -> set[int]:
    return set(
        session.execute(
            text("SELECT id FROM users WHERE role IN ('admin','super_admin') AND deleted_at IS NULL")
        ).scalars().all()
    )
