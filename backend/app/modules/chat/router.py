"""라우터는 얇게: FastAPI 배선 + 웹소켓 실시간 푸시 전달만 여기 있고,
실제 데이터/권한 로직은 service.py + permissions.py + repository.py에 있다.
2026-08-26: 예전엔 이 파일 하나(218줄)에 SQL/권한판정/직렬화/웹소켓이
전부 섞여 있었다 -- 다른 모듈들처럼 계층을 나눴다."""
import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import SessionLocal, get_db
from app.core.security import TokenValidationError, decode_access_token
from app.modules.auth import repository as auth_repository
from app.modules.chat import service
from app.modules.chat.constants import (
    CHAT_ALLOWED_MIME_TYPES,
    CHAT_MAX_ATTACHMENT_BYTES,
    CHAT_MEDIA_DIR,
    CHAT_MEDIA_URL,
    DEFAULT_MESSAGE_PAGE_SIZE,
    MAX_MESSAGE_PAGE_SIZE,
)
from app.modules.chat.schemas import (
    AttachmentResponse,
    CloseRoomResponse,
    CompanyRoomRequest,
    MessageListResponse,
    MessageRequest,
    ReadReceiptResponse,
    RoomListResponse,
    RoomSummary,
    SendMessageResponse,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# ---- 실시간 푸시(WebSocket) ----
# uvicorn이 --workers 없이 단일 프로세스로 떠 있어(SERVER_CONTEXT.md 4번)
# 워커 간 pub/sub 없이 프로세스 인메모리 dict로 충분하다. 사용자 단위로
# 소켓을 묶는다(방 하나가 아니라) -- 업체/관리자는 여러 방을 동시에
# 모니터링하는 화면 구조라서(js/portal.js) 사용자 단위가 기존 UX와 맞는다.
_ws_connections: dict[int, set[WebSocket]] = {}
_ws_loop: asyncio.AbstractEventLoop | None = None


async def _ws_send_one(uid: int, ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        conns = _ws_connections.get(uid)
        if conns:
            conns.discard(ws)
            if not conns:
                _ws_connections.pop(uid, None)


def _broadcast(user_ids: set[int], payload: dict) -> None:
    if not _ws_loop or not user_ids:
        return
    safe = jsonable_encoder(payload)
    for uid in user_ids:
        conns = _ws_connections.get(uid)
        if not conns:
            continue
        for ws in list(conns):
            asyncio.run_coroutine_threadsafe(_ws_send_one(uid, ws, safe), _ws_loop)


def _push_new_message(session: Session, room_id: int, message_id: int) -> None:
    payload = service.build_push_payload(session, room_id, message_id)
    if not payload:
        return
    recipients = payload.pop("recipients")
    _broadcast(recipients, payload)


@router.get("/rooms", response_model=RoomListResponse)
def rooms(current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return service.list_rooms(session, current_user)


@router.post("/rooms/company", response_model=RoomSummary)
def company_room(payload: CompanyRoomRequest, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return service.open_company_room(session, current_user, company_id=payload.company_id, portfolio_id=payload.portfolio_id)


@router.post("/rooms/support", response_model=RoomSummary)
def support_room(current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return service.open_support_room(session, current_user)


@router.get("/rooms/{room_id}/messages", response_model=MessageListResponse)
def messages(
    room_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_MESSAGE_PAGE_SIZE, ge=1, le=MAX_MESSAGE_PAGE_SIZE),
    before_id: int | None = Query(default=None),
) -> dict:
    # 2026-08-26: 대화가 길어져도 매번 전체 내역을 다 안 긁어오도록 페이지네이션
    # 추가(기본: 최근 50건). before_id를 주면 그보다 오래된 메시지를 더 가져온다
    # -- 지금은 어떤 대화도 50건을 넘지 않아 프론트는 기본값만 쓰고 있음.
    return service.list_messages(session, current_user, room_id, limit=limit, before_id=before_id)


@router.post("/rooms/{room_id}/messages", response_model=SendMessageResponse)
def send(room_id: int, payload: MessageRequest, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    response, message_id = service.send_text_message(
        session, current_user, room_id, content=payload.content, portfolio_id=payload.portfolio_id
    )
    _push_new_message(session, room_id, message_id)
    return response


@router.post("/rooms/{room_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(
    room_id: int, current_user: CurrentUser, upload: UploadFile = File(...), session: Session = Depends(get_db)
) -> dict:
    # 방 접근권한은 파일을 디스크에 쓰기 전에 먼저 확인해서, 권한 없는
    # 업로드 시도로 디스크가 낭비되지 않게 한다.
    room = service.get_room_or_404(session, room_id)
    service.require_access(session, current_user, room)
    service.require_send_allowed(current_user, room)

    mime = (upload.content_type or "").lower()
    if mime not in CHAT_ALLOWED_MIME_TYPES:
        raise HTTPException(422, "JPG, PNG, WEBP 이미지만 첨부할 수 있습니다.")
    data = await upload.read(CHAT_MAX_ATTACHMENT_BYTES + 1)
    if not data:
        raise HTTPException(422, "빈 파일은 첨부할 수 없습니다.")
    if len(data) > CHAT_MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "채팅 이미지는 5MB 이하만 첨부할 수 있습니다.")

    CHAT_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}.{CHAT_ALLOWED_MIME_TYPES[mime]}"
    path = CHAT_MEDIA_DIR / name
    path.write_bytes(data)
    url = f"{CHAT_MEDIA_URL}/{name}"

    try:
        response, message_id = service.save_attachment_message(
            session, current_user, room_id, url=url, mime_type=mime, file_size_bytes=len(data)
        )
        session.commit()
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise

    _push_new_message(session, room_id, message_id)
    return response


@router.post("/rooms/{room_id}/read", response_model=ReadReceiptResponse)
def read_room(room_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return service.mark_read(session, current_user, room_id)


@router.post("/rooms/{room_id}/close", response_model=CloseRoomResponse)
def close(room_id: int, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    return service.close_room(session, current_user, room_id)


@router.websocket("/ws")
async def chat_stream(websocket: WebSocket, token: str = Query(...)) -> None:
    # 브라우저 WebSocket API는 커스텀 헤더를 못 보내 Authorization 대신
    # 쿼리스트링 token으로 인증한다(F3, 2026-08-24). 연결 시점에만 검증하고
    # 이후 만료돼도 소켓을 강제로 끊진 않는다 -- 푸시 대상(수신자)은 매번
    # DB에서 방 멤버십을 다시 계산해 결정하므로(room_recipient_ids) 토큰
    # 만료 자체가 권한 상승으로 이어지지 않는다.
    global _ws_loop
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (TokenValidationError, ValueError, KeyError):
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        user = auth_repository.find_user_by_id(db, user_id)
    finally:
        db.close()
    if not user or user["status"] != "active":
        await websocket.close(code=4401)
        return

    await websocket.accept()
    _ws_loop = asyncio.get_running_loop()
    _ws_connections.setdefault(user_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        conns = _ws_connections.get(user_id)
        if conns:
            conns.discard(websocket)
            if not conns:
                _ws_connections.pop(user_id, None)
