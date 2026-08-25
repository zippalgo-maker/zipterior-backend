from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AnalyticsEventType = Literal[
    "page_view",
    "search",
    "search_select",
    "company_view",
    "company_dwell",
    "portfolio_view",
    "portfolio_dwell",
    "inquiry_submit",
]


class AnalyticsEventCreate(BaseModel):
    """Public event fields are deliberately narrow to prevent arbitrary data capture."""

    client_event_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    event_type: AnalyticsEventType
    entity_type: Literal["page", "company", "portfolio", "complex"] = "page"
    entity_id: int | None = Field(default=None, ge=1)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    search_query: str | None = Field(default=None, max_length=200)
    page_path: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("search_query", "page_path", "referrer")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


class AnalyticsEventBatch(BaseModel):
    events: list[AnalyticsEventCreate] = Field(min_length=1, max_length=20)


class AnalyticsEventAccepted(BaseModel):
    accepted: int


class AnalyticsSeriesPoint(BaseModel):
    label: str
    sessions: int
    company_views: int
    portfolio_views: int
    dwell_seconds: int
    engagement_adds: int
    engagement_removes: int
    searches: int


class AnalyticsContentItem(BaseModel):
    entity_type: Literal["company", "portfolio"]
    entity_id: int
    title: str
    views: int
    dwell_seconds: int
    engagement_adds: int
    engagement_removes: int
    href: str


class AnalyticsRankItem(BaseModel):
    label: str
    count: int


class AnalyticsRecentEngagement(BaseModel):
    occurred_at: str
    action: str
    entity_type: Literal["company", "portfolio"]
    entity_id: int
    title: str
    href: str


class AnalyticsSummary(BaseModel):
    sessions: int
    page_views: int
    company_views: int
    portfolio_views: int
    company_dwell_seconds: int
    portfolio_dwell_seconds: int
    average_company_dwell_seconds: int
    average_portfolio_dwell_seconds: int
    engagement_adds: int
    engagement_removes: int
    searches: int
    inquiries: int


class AnalyticsReport(BaseModel):
    date_from: date
    date_to: date
    interval: Literal["day", "week", "month"]
    scope: Literal["admin", "company"]
    company_id: int | None
    summary: AnalyticsSummary
    series: list[AnalyticsSeriesPoint]
    content: list[AnalyticsContentItem]
    search_terms: list[AnalyticsRankItem]
    traffic_sources: list[AnalyticsRankItem]
    browsers: list[AnalyticsRankItem]
    operating_systems: list[AnalyticsRankItem]
    devices: list[AnalyticsRankItem]
    recent_engagement: list[AnalyticsRecentEngagement]
