from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.common.dependencies import CurrentUser
from app.core.database import get_db

router = APIRouter(tags=["company-favorites"])

def _company(session: Session, company_id: int):
    return session.execute(text("""SELECT id,name,phone,address,sido,sigungu,intro,logo_path,status FROM companies WHERE id=:id AND deleted_at IS NULL LIMIT 1"""), {"id": company_id}).mappings().one_or_none()

@router.get("/api/v1/companies/{company_id}/favorite")
def status_favorite(company_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    row=session.execute(text("SELECT 1 FROM company_favorites WHERE user_id=:u AND company_id=:c"),{"u":current_user["id"],"c":company_id}).first()
    return {"company_id":company_id,"is_favorite":bool(row)}

@router.post("/api/v1/companies/{company_id}/favorite",status_code=status.HTTP_201_CREATED)
def add_favorite(company_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    if not _company(session,company_id): raise HTTPException(404,"업체를 찾을 수 없습니다.")
    session.execute(text("INSERT INTO company_favorites(user_id,company_id) VALUES(:u,:c) ON CONFLICT DO NOTHING"),{"u":current_user["id"],"c":company_id}); session.commit()
    return {"company_id":company_id,"is_favorite":True}

@router.delete("/api/v1/companies/{company_id}/favorite")
def remove_favorite(company_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    session.execute(text("DELETE FROM company_favorites WHERE user_id=:u AND company_id=:c"),{"u":current_user["id"],"c":company_id}); session.commit()
    return {"company_id":company_id,"is_favorite":False}

@router.get("/api/v1/me/favorite-companies")
def list_favorites(current_user:CurrentUser,limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_db)):
    rows=session.execute(text("""SELECT c.id,c.name,c.phone,c.address,c.sido,c.sigungu,c.intro,c.logo_path,c.status,cf.created_at FROM company_favorites cf JOIN companies c ON c.id=cf.company_id WHERE cf.user_id=:u AND c.deleted_at IS NULL ORDER BY cf.created_at DESC LIMIT :l OFFSET :o"""),{"u":current_user["id"],"l":limit,"o":offset}).mappings().all()
    return {"items":[dict(r) for r in rows],"limit":limit,"offset":offset}
