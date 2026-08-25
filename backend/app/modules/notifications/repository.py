from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def create_notification(session: Session, *, user_id: int, notification_type: str, title: str, message: str | None, target_type: str | None, target_id: int | None) -> int:
    return int(session.execute(text("""
        INSERT INTO notifications (user_id, notification_type, title, message, target_type, target_id)
        VALUES (:user_id, :notification_type, :title, :message, :target_type, :target_id)
        RETURNING id
    """), {"user_id":user_id,"notification_type":notification_type,"title":title,"message":message,"target_type":target_type,"target_id":target_id}).scalar_one())


def unread_notification_exists(
    session: Session,
    *,
    user_id: int,
    notification_type: str,
    target_type: str | None,
) -> bool:
    # 같은 연동 장애가 반복되어도 관리자가 확인하기 전에는 알림을 중복 생성하지 않는다.
    return bool(session.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM notifications
            WHERE user_id=:user_id
              AND notification_type=:notification_type
              AND target_type IS NOT DISTINCT FROM :target_type
              AND read_at IS NULL
        )
    """), {
        "user_id": user_id,
        "notification_type": notification_type,
        "target_type": target_type,
    }).scalar_one())


def list_notifications(session: Session, *, user_id: int, unread_only: bool, limit: int, offset: int) -> list[dict[str, Any]]:
    where="user_id=:user_id" + (" AND read_at IS NULL" if unread_only else "")
    rows=session.execute(text(f"SELECT id, notification_type, title, message, target_type, target_id, read_at, created_at FROM notifications WHERE {where} ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"), {"user_id":user_id,"limit":limit,"offset":offset}).mappings().all()
    return [dict(r) for r in rows]


def count_notifications(session: Session, *, user_id: int, unread_only: bool=False) -> int:
    where="user_id=:user_id" + (" AND read_at IS NULL" if unread_only else "")
    return int(session.execute(text(f"SELECT COUNT(*) FROM notifications WHERE {where}"), {"user_id":user_id}).scalar_one())


def mark_read(session: Session, *, user_id: int, notification_id: int) -> int:
    result=session.execute(text("UPDATE notifications SET read_at=COALESCE(read_at,NOW()) WHERE id=:id AND user_id=:user_id"), {"id":notification_id,"user_id":user_id})
    return int(result.rowcount)


def mark_all_read(session: Session, *, user_id: int) -> int:
    result=session.execute(text("UPDATE notifications SET read_at=NOW() WHERE user_id=:user_id AND read_at IS NULL"), {"user_id":user_id})
    return int(result.rowcount)


def company_member_user_ids(session: Session, *, company_ids: list[int]) -> list[int]:
    if not company_ids: return []
    stmt=text("""
      SELECT DISTINCT cm.user_id
      FROM company_members cm JOIN users u ON u.id=cm.user_id
      WHERE cm.company_id IN :ids AND cm.status='active'
        AND cm.member_role IN ('owner','manager') AND u.status='active'
    """).bindparams(bindparam("ids", expanding=True))
    return [int(r[0]) for r in session.execute(stmt,{"ids":company_ids}).all()]
