from sqlalchemy.orm import Session

from app.modules.notifications import repository


class NotificationNotFoundError(ValueError):
    pass


class NotificationService:
    @staticmethod
    def create(session: Session, *, user_id: int, notification_type: str, title: str, message: str | None=None, target_type: str | None=None, target_id: int | None=None) -> int:
        return repository.create_notification(session, user_id=user_id, notification_type=notification_type, title=title, message=message, target_type=target_type, target_id=target_id)

    @staticmethod
    def create_unread_once(session: Session, *, user_id: int, notification_type: str, title: str, message: str | None=None, target_type: str | None=None, target_id: int | None=None) -> int | None:
        if repository.unread_notification_exists(
            session,
            user_id=user_id,
            notification_type=notification_type,
            target_type=target_type,
        ):
            return None
        return NotificationService.create(
            session,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            target_type=target_type,
            target_id=target_id,
        )

    @staticmethod
    def notify_companies(session: Session, *, company_ids: list[int], notification_type: str, title: str, message: str | None=None, target_type: str | None=None, target_id: int | None=None) -> int:
        count=0
        for user_id in repository.company_member_user_ids(session, company_ids=company_ids):
            NotificationService.create(session,user_id=user_id,notification_type=notification_type,title=title,message=message,target_type=target_type,target_id=target_id)
            count+=1
        return count

    @staticmethod
    def list_mine(session: Session, *, user: dict, unread_only: bool, limit: int, offset: int) -> dict:
        return {
            "items":repository.list_notifications(session,user_id=user["id"],unread_only=unread_only,limit=limit,offset=offset),
            "total":repository.count_notifications(session,user_id=user["id"],unread_only=unread_only),
            "unread_count":repository.count_notifications(session,user_id=user["id"],unread_only=True),
            "limit":limit,"offset":offset,
        }

    @staticmethod
    def read_one(session: Session, *, user: dict, notification_id: int) -> dict:
        updated=repository.mark_read(session,user_id=user["id"],notification_id=notification_id)
        if not updated: raise NotificationNotFoundError("알림을 찾을 수 없습니다.")
        session.commit()
        return {"updated_count":updated,"unread_count":repository.count_notifications(session,user_id=user["id"],unread_only=True),"message":"알림을 읽음 처리했습니다."}

    @staticmethod
    def read_all(session: Session, *, user: dict) -> dict:
        updated=repository.mark_all_read(session,user_id=user["id"])
        session.commit()
        return {"updated_count":updated,"unread_count":0,"message":"모든 알림을 읽음 처리했습니다."}
