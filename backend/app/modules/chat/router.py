import asyncio
from fastapi import APIRouter, Depends, HTTPException, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from pathlib import Path
from uuid import uuid4
from app.common.dependencies import CurrentUser
from app.core.database import get_db, SessionLocal
from app.core.security import TokenValidationError, decode_access_token
from app.modules.auth import repository as auth_repository

router=APIRouter(prefix="/api/v1/chat",tags=["chat"])

# ---- 실시간 푸시(WebSocket) ----
# uvicorn이 --workers 없이 단일 프로세스로 떠 있어(SERVER_CONTEXT.md 4번)
# 워커 간 pub/sub 없이 프로세스 인메모리 dict로 충분하다. 사용자 단위로
# 소켓을 묶는다(방 하나가 아니라) -- 업체/관리자는 여러 방을 동시에
# 모니터링하는 화면 구조라서(js/portal.js) 사용자 단위가 기존 UX와 맞는다.
_ws_connections:dict[int,set[WebSocket]]={}
_ws_loop:asyncio.AbstractEventLoop|None=None

def _room_recipients(session,r)->set[int]:
    ids=set()
    if r["room_type"]=="company":
        if r.get("customer_id"): ids.add(r["customer_id"])
        cid=r.get("company_id")
        if cid:
            owner=session.execute(text("SELECT owner_user_id FROM companies WHERE id=:c"),{"c":cid}).scalar()
            if owner: ids.add(owner)
            ids.update(session.execute(text("SELECT user_id FROM company_members WHERE company_id=:c AND status='active'"),{"c":cid}).scalars().all())
    elif r["room_type"]=="support":
        if r.get("requester_user_id"): ids.add(r["requester_user_id"])
        ids.update(session.execute(text("SELECT id FROM users WHERE role IN ('admin','super_admin') AND deleted_at IS NULL")).scalars().all())
    return ids

async def _ws_send_one(uid:int,ws:WebSocket,payload:dict):
    try:
        await ws.send_json(payload)
    except Exception:
        conns=_ws_connections.get(uid)
        if conns:
            conns.discard(ws)
            if not conns: _ws_connections.pop(uid,None)

def _broadcast(user_ids:set[int],payload:dict):
    if not _ws_loop or not user_ids: return
    safe=jsonable_encoder(payload)
    for uid in user_ids:
        conns=_ws_connections.get(uid)
        if not conns: continue
        for ws in list(conns):
            asyncio.run_coroutine_threadsafe(_ws_send_one(uid,ws,safe),_ws_loop)

def _notify_new_message(session,room_id:int,message_id:int):
    r=_room(session,room_id)
    if not r: return
    row=session.execute(text("""SELECT m.id,m.sender_user_id,u.role AS sender_role,m.message_type,m.content,m.portfolio_id,m.created_at, a.file_path,a.thumbnail_path,a.mime_type,a.file_size_bytes FROM chat_messages m JOIN users u ON u.id=m.sender_user_id LEFT JOIN chat_attachments a ON a.message_id=m.id WHERE m.id=:id"""),{"id":message_id}).mappings().one_or_none()
    if not row: return
    message={"id":row["id"],"sender":row["sender_role"],"type":row["message_type"],"text":row["content"] or "","portfolioId":row["portfolio_id"],"image":row["file_path"] or "","thumbnail":row["thumbnail_path"] or "","mimeType":row["mime_type"],"fileSize":row["file_size_bytes"],"createdAt":row["created_at"]}
    payload={"type":"chat_message","roomId":room_id,"message":message,"room":_serialize(session,r,None)}
    _broadcast(_room_recipients(session,r),payload)

class CompanyRoomRequest(BaseModel):
    company_id:int
    portfolio_id:int|None=None
class MessageRequest(BaseModel):
    content:str=Field(min_length=1,max_length=2000)
    portfolio_id:int|None=None

def _company_id(session,user):
    if user["role"]!="company": return None
    return session.execute(text("""SELECT c.id FROM companies c LEFT JOIN company_members cm ON cm.company_id=c.id AND cm.user_id=:u AND cm.status='active' WHERE c.owner_user_id=:u OR cm.user_id=:u ORDER BY (c.owner_user_id=:u) DESC LIMIT 1"""),{"u":user["id"]}).scalar()

def _room(session,room_id):
    r=session.execute(text("SELECT * FROM chat_rooms WHERE id=:id"),{"id":room_id}).mappings().one_or_none(); return dict(r) if r else None

def _allowed(session,user,r):
    if user["role"] in ("admin","super_admin"): return r["room_type"]=="support"
    if user["role"]=="customer": return r.get("customer_id")==user["id"] or (r["room_type"]=="support" and r.get("requester_user_id")==user["id"])
    if user["role"]=="company": return (r["room_type"]=="company" and r.get("company_id")==_company_id(session,user)) or (r["room_type"]=="support" and r.get("requester_user_id")==user["id"])
    return False

def _serialize(session,r,user):
    last=session.execute(text("SELECT id,content,message_type,created_at FROM chat_messages WHERE chat_room_id=:r AND deleted_at IS NULL ORDER BY id DESC LIMIT 1"),{"r":r["id"]}).mappings().one_or_none()
    customer=session.execute(text("SELECT name FROM users WHERE id=:id"),{"id":r.get("customer_id") or r.get("requester_user_id")}).scalar()
    company=session.execute(text("SELECT name,phone FROM companies WHERE id=:id"),{"id":r.get("company_id")}).mappings().one_or_none() if r.get("company_id") else None
    return {"id":r["id"],"channel":r["room_type"],"customerId":r.get("customer_id"),"customerName":customer or "고객","requesterId":r.get("requester_user_id"),"requesterName":customer or "회원","requesterRole":"company" if r["room_type"]=="support" and session.execute(text("SELECT role FROM users WHERE id=:id"),{"id":r.get("requester_user_id")}).scalar()=="company" else "customer","companyId":r.get("company_id"),"companyName":company["name"] if company else "고객센터","companyPhone":company["phone"] if company else "","status":r["status"],"supportActive":r["status"]=="active","updatedAt":r.get("last_message_at") or r["created_at"],"lastMessage":dict(last) if last else None}

@router.get("/rooms")
def rooms(current_user:CurrentUser,session:Session=Depends(get_db)):
    if current_user["role"] in ("admin","super_admin"):
        rows=session.execute(text("SELECT * FROM chat_rooms WHERE room_type='support' ORDER BY COALESCE(last_message_at,created_at) DESC")).mappings().all()
    elif current_user["role"]=="customer":
        rows=session.execute(text("SELECT * FROM chat_rooms WHERE customer_id=:u OR (room_type='support' AND requester_user_id=:u) ORDER BY COALESCE(last_message_at,created_at) DESC"),{"u":current_user["id"]}).mappings().all()
    elif current_user["role"]=="company":
        cid=_company_id(session,current_user)
        rows=session.execute(text("SELECT * FROM chat_rooms WHERE (room_type='company' AND company_id=:c) OR (room_type='support' AND requester_user_id=:u) ORDER BY COALESCE(last_message_at,created_at) DESC"),{"c":cid,"u":current_user["id"]}).mappings().all()
    else: rows=[]
    return {"items":[_serialize(session,dict(r),current_user) for r in rows]}

@router.post("/rooms/company")
def company_room(payload:CompanyRoomRequest,current_user:CurrentUser,session:Session=Depends(get_db)):
    if current_user["role"]!="customer": raise HTTPException(403,"일반회원만 업체 상담을 시작할 수 있습니다.")
    if not session.execute(text("SELECT 1 FROM companies WHERE id=:c AND deleted_at IS NULL"),{"c":payload.company_id}).first(): raise HTTPException(404,"업체를 찾을 수 없습니다.")
    r=session.execute(text("SELECT * FROM chat_rooms WHERE room_type='company' AND customer_id=:u AND company_id=:c AND status<>'blocked' ORDER BY id DESC LIMIT 1"),{"u":current_user["id"],"c":payload.company_id}).mappings().one_or_none()
    if not r:
        rid=session.execute(text("INSERT INTO chat_rooms(room_type,customer_id,company_id,requester_user_id,portfolio_id,status) VALUES('company',:u,:c,:u,:p,'active') RETURNING id"),{"u":current_user["id"],"c":payload.company_id,"p":payload.portfolio_id}).scalar_one(); session.execute(text("INSERT INTO chat_room_members(chat_room_id,user_id,member_role) VALUES(:r,:u,'customer') ON CONFLICT DO NOTHING"),{"r":rid,"u":current_user["id"]}); session.commit(); r=_room(session,rid)
    return _serialize(session,dict(r),current_user)

@router.post("/rooms/support")
def support_room(current_user:CurrentUser,session:Session=Depends(get_db)):
    r=session.execute(text("SELECT * FROM chat_rooms WHERE room_type='support' AND requester_user_id=:u AND status<>'blocked' ORDER BY id DESC LIMIT 1"),{"u":current_user["id"]}).mappings().one_or_none()
    if not r:
        rid=session.execute(text("INSERT INTO chat_rooms(room_type,customer_id,requester_user_id,status) VALUES('support',:cust,:u,'active') RETURNING id"),{"cust":current_user["id"] if current_user["role"]=='customer' else None,"u":current_user["id"]}).scalar_one(); session.execute(text("INSERT INTO chat_room_members(chat_room_id,user_id,member_role) VALUES(:r,:u,:role) ON CONFLICT DO NOTHING"),{"r":rid,"u":current_user["id"],"role":current_user["role"]}); session.commit(); r=_room(session,rid)
    return _serialize(session,dict(r),current_user)

@router.get("/rooms/{room_id}/messages")
def messages(room_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    r=_room(session,room_id)
    if not r: raise HTTPException(404,"채팅방을 찾을 수 없습니다.")
    if not _allowed(session,current_user,r): raise HTTPException(403,"채팅방 접근 권한이 없습니다.")
    rows=session.execute(text("""SELECT m.id,m.sender_user_id,u.role AS sender_role,m.message_type,m.content,m.portfolio_id,m.created_at, a.file_path,a.thumbnail_path,a.mime_type,a.file_size_bytes FROM chat_messages m JOIN users u ON u.id=m.sender_user_id LEFT JOIN chat_attachments a ON a.message_id=m.id WHERE m.chat_room_id=:r AND m.deleted_at IS NULL ORDER BY m.id"""),{"r":room_id}).mappings().all()
    return {"items":[{"id":x["id"],"sender":x["sender_role"],"type":x["message_type"],"text":x["content"] or "","portfolioId":x["portfolio_id"],"image":x["file_path"] or "","thumbnail":x["thumbnail_path"] or "","mimeType":x["mime_type"],"fileSize":x["file_size_bytes"],"createdAt":x["created_at"]} for x in rows]}

@router.post("/rooms/{room_id}/messages")
def send(room_id:int,payload:MessageRequest,current_user:CurrentUser,session:Session=Depends(get_db)):
    r=_room(session,room_id)
    if not r: raise HTTPException(404,"채팅방을 찾을 수 없습니다.")
    if not _allowed(session,current_user,r): raise HTTPException(403,"채팅방 접근 권한이 없습니다.")
    if r["room_type"]=="company" and current_user["role"] in ("admin","super_admin"): raise HTTPException(403,"관리자는 업체 채팅을 모니터링만 할 수 있습니다.")
    mid=session.execute(text("INSERT INTO chat_messages(chat_room_id,sender_user_id,message_type,content,portfolio_id) VALUES(:r,:u,'text',:c,:p) RETURNING id"),{"r":room_id,"u":current_user["id"],"c":payload.content.strip(),"p":payload.portfolio_id}).scalar_one(); session.execute(text("UPDATE chat_rooms SET last_message_at=now(),status='active',closed_at=NULL WHERE id=:r"),{"r":room_id}); session.commit()
    _notify_new_message(session,room_id,mid)
    return {"id":mid,"room_id":room_id,"sent":True}


CHAT_MEDIA_DIR=Path("/srv/zipterior/media/chat")
CHAT_MEDIA_URL="/media/chat"
CHAT_ALLOWED={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}
CHAT_MAX_BYTES=5*1024*1024

@router.post("/rooms/{room_id}/attachments")
async def upload_attachment(room_id:int,current_user:CurrentUser,upload:UploadFile=File(...),session:Session=Depends(get_db)):
    r=_room(session,room_id)
    if not r: raise HTTPException(404,"채팅방을 찾을 수 없습니다.")
    if not _allowed(session,current_user,r): raise HTTPException(403,"채팅방 접근 권한이 없습니다.")
    if r["room_type"]=="company" and current_user["role"] in ("admin","super_admin"): raise HTTPException(403,"관리자는 업체 채팅을 모니터링만 할 수 있습니다.")
    mime=(upload.content_type or "").lower()
    if mime not in CHAT_ALLOWED: raise HTTPException(422,"JPG, PNG, WEBP 이미지만 첨부할 수 있습니다.")
    data=await upload.read(CHAT_MAX_BYTES+1)
    if not data: raise HTTPException(422,"빈 파일은 첨부할 수 없습니다.")
    if len(data)>CHAT_MAX_BYTES: raise HTTPException(413,"채팅 이미지는 5MB 이하만 첨부할 수 있습니다.")
    CHAT_MEDIA_DIR.mkdir(parents=True,exist_ok=True)
    name=f"{uuid4().hex}.{CHAT_ALLOWED[mime]}"
    path=CHAT_MEDIA_DIR/name
    path.write_bytes(data)
    url=f"{CHAT_MEDIA_URL}/{name}"
    try:
        mid=session.execute(text("INSERT INTO chat_messages(chat_room_id,sender_user_id,message_type,content) VALUES(:r,:u,'image','') RETURNING id"),{"r":room_id,"u":current_user["id"]}).scalar_one()
        session.execute(text("INSERT INTO chat_attachments(message_id,file_path,mime_type,file_size_bytes) VALUES(:m,:p,:t,:s)"),{"m":mid,"p":url,"t":mime,"s":len(data)})
        session.execute(text("UPDATE chat_rooms SET last_message_at=now(),status='active',closed_at=NULL WHERE id=:r"),{"r":room_id})
        session.commit()
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    _notify_new_message(session,room_id,mid)
    return {"id":mid,"room_id":room_id,"type":"image","image":url,"mime_type":mime,"file_size_bytes":len(data)}

@router.post("/rooms/{room_id}/read")
def read_room(room_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    r=_room(session,room_id)
    if not r or not _allowed(session,current_user,r): raise HTTPException(403,"채팅방 접근 권한이 없습니다.")
    last=session.execute(text("SELECT max(id) FROM chat_messages WHERE chat_room_id=:r"),{"r":room_id}).scalar()
    session.execute(text("INSERT INTO chat_room_members(chat_room_id,user_id,member_role,last_read_message_id) VALUES(:r,:u,:role,:m) ON CONFLICT(chat_room_id,user_id) DO UPDATE SET last_read_message_id=EXCLUDED.last_read_message_id,left_at=NULL"),{"r":room_id,"u":current_user["id"],"role":current_user["role"],"m":last}); session.commit(); return {"read":True}

@router.post("/rooms/{room_id}/close")
def close(room_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    r=_room(session,room_id)
    if not r or r["room_type"]!="support" or current_user["role"] not in ("admin","super_admin"): raise HTTPException(403,"관리자 권한이 필요합니다.")
    session.execute(text("UPDATE chat_rooms SET status='closed',closed_at=now() WHERE id=:r"),{"r":room_id}); session.commit(); return {"closed":True}

@router.websocket("/ws")
async def chat_stream(websocket:WebSocket,token:str=Query(...)):
    # 브라우저 WebSocket API는 커스텀 헤더를 못 보내 Authorization 대신
    # 쿼리스트링 token으로 인증한다(F3, 2026-08-24). 연결 시점에만 검증하고
    # 이후 만료돼도 소켓을 강제로 끊진 않는다 -- 푸시 대상(수신자)은 매번
    # DB에서 방 멤버십을 다시 계산해 결정하므로(_room_recipients) 토큰
    # 만료 자체가 권한 상승으로 이어지지 않는다.
    global _ws_loop
    try:
        payload=decode_access_token(token)
        user_id=int(payload["sub"])
    except (TokenValidationError,ValueError,KeyError):
        await websocket.close(code=4401); return
    db=SessionLocal()
    try:
        user=auth_repository.find_user_by_id(db,user_id)
    finally:
        db.close()
    if not user or user["status"]!="active":
        await websocket.close(code=4401); return
    await websocket.accept()
    _ws_loop=asyncio.get_running_loop()
    _ws_connections.setdefault(user_id,set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        conns=_ws_connections.get(user_id)
        if conns:
            conns.discard(websocket)
            if not conns: _ws_connections.pop(user_id,None)
