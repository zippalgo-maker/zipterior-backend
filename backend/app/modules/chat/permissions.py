"""회원 role과 채팅방 소유관계를 대조하는 접근권한 판정만 모아둔다.
DB 조회가 섞여 있는 건 room_type별 소유자를 확인하려면 어쩔 수 없지만,
'이 요청을 허용할지' 판단 자체는 여기서만 한다."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def company_id_for_user(session: Session, user: dict) -> int | None:
    """이 업체 회원이 속한 업체 id(대표 or 소속 직원). 업체가 아니면 None."""
    if user["role"] != "company":
        return None
    return session.execute(
        text(
            """
            SELECT c.id FROM companies c
            LEFT JOIN company_members cm
              ON cm.company_id = c.id AND cm.user_id = :u AND cm.status = 'active'
            WHERE c.owner_user_id = :u OR cm.user_id = :u
            ORDER BY (c.owner_user_id = :u) DESC
            LIMIT 1
            """
        ),
        {"u": user["id"]},
    ).scalar()


def can_access_room(session: Session, user: dict, room: dict) -> bool:
    role = user["role"]
    # 2026-08-26: "채팅 모니터링" 화면(회원↔업체 대화 읽기전용 확인)이
    # 이 조건 때문에 처음부터 아예 동작하지 않고 있었다 -- support만
    # 허용돼서 company 방은 관리자가 목록/메시지 둘 다 못 봤음(발신 차단은
    # can_send_in_room에서 이미 따로 하고 있어서 여기서 company를 열어줘도
    # 관리자가 쓸 수 있게 되는 게 아니라 "보이기만" 하게 된다).
    if role in ("admin", "super_admin"):
        return room["room_type"] in ("support", "company")
    if role == "customer":
        return room.get("customer_id") == user["id"] or (
            room["room_type"] == "support" and room.get("requester_user_id") == user["id"]
        )
    if role == "company":
        return (
            room["room_type"] == "company"
            and room.get("company_id") == company_id_for_user(session, user)
        ) or (room["room_type"] == "support" and room.get("requester_user_id") == user["id"])
    return False


def can_send_in_room(user: dict, room: dict) -> bool:
    """회원↔업체 채팅(company room)은 관리자가 읽기 전용으로만 모니터링한다."""
    if room["room_type"] == "company" and user["role"] in ("admin", "super_admin"):
        return False
    return True
