from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.common.dependencies import CurrentUser
from app.core.database import get_db
router=APIRouter(prefix="/api/v1/me",tags=["users"])
class ProfileUpdate(BaseModel):
    name:str|None=Field(default=None,min_length=2,max_length=100)
    nickname:str|None=Field(default=None,max_length=100)
    phone:str|None=Field(default=None,max_length=30)
    marketing_agreed:bool|None=None
@router.patch("/profile")
def update_profile(payload:ProfileUpdate,current_user:CurrentUser,session:Session=Depends(get_db)):
    data=payload.model_dump(exclude_unset=True)
    if not data: raise HTTPException(422,"수정할 정보가 없습니다.")
    sets=[]; params={"id":current_user["id"]}
    for k,v in data.items(): sets.append(f"{k}=:{k}"); params[k]=v
    sets.append("updated_at=now()")
    row=session.execute(text(f"UPDATE users SET {','.join(sets)} WHERE id=:id AND deleted_at IS NULL RETURNING id,email,name,nickname,phone,role,status,marketing_agreed,email_verified_at,created_at"),params).mappings().one_or_none()
    if not row: raise HTTPException(404,"사용자를 찾을 수 없습니다.")
    session.commit(); return dict(row)
