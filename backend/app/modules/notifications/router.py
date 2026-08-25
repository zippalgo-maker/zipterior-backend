from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.notifications.schemas import NotificationActionResponse, NotificationListResponse
from app.modules.notifications.service import NotificationNotFoundError, NotificationService

router=APIRouter(prefix="/api/v1/notifications",tags=["notifications"])

@router.get("",response_model=NotificationListResponse)
def list_notifications(current_user:CurrentUser,unread_only:bool=Query(default=False),limit:int=Query(default=30,ge=1,le=100),offset:int=Query(default=0,ge=0),session:Session=Depends(get_db))->dict:
    return NotificationService.list_mine(session,user=current_user,unread_only=unread_only,limit=limit,offset=offset)

@router.post("/{notification_id}/read",response_model=NotificationActionResponse)
def read_notification(notification_id:int,current_user:CurrentUser,session:Session=Depends(get_db))->dict:
    try: return NotificationService.read_one(session,user=current_user,notification_id=notification_id)
    except NotificationNotFoundError as exc: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=str(exc)) from exc

@router.post("/read-all",response_model=NotificationActionResponse)
def read_all_notifications(current_user:CurrentUser,session:Session=Depends(get_db))->dict:
    return NotificationService.read_all(session,user=current_user)
