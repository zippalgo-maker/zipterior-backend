from datetime import datetime
from pydantic import BaseModel, Field


class DiskUsageItem(BaseModel):
    mount: str
    label: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    level: str  # "ok" | "warning" | "critical"


class CleanupCandidate(BaseModel):
    id: str
    type: str  # "pycache" | "bak_file" | "release" | "import_job"
    label: str
    size_bytes: int
    modified_at: datetime | None = None
    blocked: bool = False
    blocked_reason: str | None = None


class DbStats(BaseModel):
    customer_members: int
    company_members: int
    companies: int
    portfolios: int
    portfolio_images: int


class CleanupHistoryDeletedItem(BaseModel):
    id: str
    label: str
    freed_bytes: int


class CleanupHistorySkippedItem(BaseModel):
    id: str
    reason: str


class CleanupHistoryEntry(BaseModel):
    id: int
    admin_label: str
    reason: str | None = None
    deleted: list[CleanupHistoryDeletedItem]
    skipped: list[CleanupHistorySkippedItem]
    freed_bytes: int
    created_at: datetime


class ServerStatusResponse(BaseModel):
    disks: list[DiskUsageItem]
    db_stats: DbStats
    cleanup_candidates: list[CleanupCandidate]
    cleanup_total_bytes: int
    cleanup_history: list[CleanupHistoryEntry]
    checked_at: datetime


class ServerCleanupRequest(BaseModel):
    targets: list[str] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=2, max_length=1000)
    password: str = Field(min_length=1, max_length=200)


class ServerCleanupResult(BaseModel):
    id: str
    label: str
    freed_bytes: int


class ServerCleanupSkipped(BaseModel):
    id: str
    reason: str


class ServerCleanupResponse(BaseModel):
    deleted: list[ServerCleanupResult]
    skipped: list[ServerCleanupSkipped]
    freed_bytes: int
    message: str
