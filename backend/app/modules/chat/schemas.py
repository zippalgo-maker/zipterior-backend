from datetime import datetime
from pydantic import BaseModel, Field


class CompanyRoomRequest(BaseModel):
    company_id: int
    portfolio_id: int | None = None


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    portfolio_id: int | None = None


class LastMessageSummary(BaseModel):
    id: int
    content: str | None = None
    message_type: str
    created_at: datetime


class RoomSummary(BaseModel):
    id: int
    channel: str
    customerId: int | None = None
    customerName: str
    requesterId: int | None = None
    requesterName: str
    requesterRole: str
    companyId: int | None = None
    companyName: str
    companyPhone: str
    status: str
    supportActive: bool
    updatedAt: datetime
    lastMessage: LastMessageSummary | None = None


class RoomListResponse(BaseModel):
    items: list[RoomSummary]


class MessageItem(BaseModel):
    id: int
    sender: str
    type: str
    text: str
    portfolioId: int | None = None
    image: str
    thumbnail: str
    mimeType: str | None = None
    fileSize: int | None = None
    createdAt: datetime


class MessageListResponse(BaseModel):
    items: list[MessageItem]
    hasMore: bool


class SendMessageResponse(BaseModel):
    id: int
    room_id: int
    sent: bool


class AttachmentResponse(BaseModel):
    id: int
    room_id: int
    type: str
    image: str
    mime_type: str
    file_size_bytes: int


class ReadReceiptResponse(BaseModel):
    read: bool


class CloseRoomResponse(BaseModel):
    closed: bool
