from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


EstimateStatus = Literal[
    "draft",
    "submitted",
    "distributing",
    "consulting",
    "contracted",
    "closed",
    "cancelled",
]

AssignmentStatus = Literal[
    "unread",
    "viewed",
    "responded",
    "declined",
    "contracted",
    "expired",
]


class EstimateCreateRequest(BaseModel):
    portfolio_id: int | None = Field(default=None, ge=1)
    complex_id: int | None = Field(default=None, ge=1)
    apartment_type_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=5000)
    desired_budget_min: Decimal | None = Field(default=None, ge=0)
    desired_budget_max: Decimal | None = Field(default=None, ge=0)
    desired_start_date: date | None = None
    contact_method: Literal["phone", "chat", "either"] | None = None
    allow_recommendations: bool = True

    @model_validator(mode="after")
    def validate_budget(self):
        if (
            self.desired_budget_min is not None
            and self.desired_budget_max is not None
            and self.desired_budget_min > self.desired_budget_max
        ):
            raise ValueError("최소 예산은 최대 예산보다 클 수 없습니다.")
        return self


class EstimateCompanySummary(BaseModel):
    id: int
    name: str
    phone: str | None = None
    logo_path: str | None = None


class EstimateImageResponse(BaseModel):
    id: int
    file_path: str
    thumbnail_path: str | None = None
    created_at: datetime


class EstimateImageUploadResponse(BaseModel):
    estimate_id: int
    image: EstimateImageResponse
    image_count: int
    message: str


class EstimateImageDeleteResponse(BaseModel):
    estimate_id: int
    image_id: int
    image_count: int
    message: str


class EstimateAssignmentResponse(BaseModel):
    company: EstimateCompanySummary
    assignment_order: int | None = None
    assignment_score: Decimal | None = None
    status: AssignmentStatus
    assigned_at: datetime
    viewed_at: datetime | None = None
    responded_at: datetime | None = None


class EstimateResponse(BaseModel):
    id: int
    customer_id: int
    portfolio_id: int | None = None
    complex_id: int | None = None
    complex_name: str | None = None
    apartment_type_id: int | None = None
    apartment_type_name: str | None = None
    pyeong_label: str | None = None
    title: str | None = None
    description: str | None = None
    desired_budget_min: Decimal | None = None
    desired_budget_max: Decimal | None = None
    desired_start_date: date | None = None
    contact_method: str | None = None
    allow_recommendations: bool
    status: EstimateStatus
    assignment_count: int = 0
    assignments: list[EstimateAssignmentResponse] = Field(default_factory=list)
    images: list[EstimateImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EstimateListResponse(BaseModel):
    items: list[EstimateResponse]
    total: int
    limit: int
    offset: int


class EstimateCancelResponse(BaseModel):
    estimate_id: int
    status: Literal["cancelled"]
    message: str


class CompanyEstimateResponse(EstimateResponse):
    assignment_status: AssignmentStatus
    assignment_order: int | None = None
    assignment_score: Decimal | None = None
    assigned_at: datetime
    viewed_at: datetime | None = None
    responded_at: datetime | None = None


class CompanyEstimateListResponse(BaseModel):
    items: list[CompanyEstimateResponse]
    total: int
    limit: int
    offset: int


class CompanyInsightsWindow(BaseModel):
    assigned_count: int
    responded_count: int
    declined_count: int
    avg_response_hours: float | None


class CompanyInsightsResponse(BaseModel):
    this_week: CompanyInsightsWindow
    last_week: CompanyInsightsWindow
    pending_over_24h: int
    avg_portfolio_images: float | None
    hints: list[str]


class CompanyEstimateActionResponse(BaseModel):
    estimate_id: int
    company_id: int
    assignment_status: AssignmentStatus
    estimate_status: EstimateStatus
    message: str


class AdminEstimateAssignRequest(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def dedupe_company_ids(self):
        self.company_ids = list(dict.fromkeys(self.company_ids))
        return self


class AdminEstimateAssignResponse(BaseModel):
    estimate_id: int
    status: EstimateStatus
    assigned_company_ids: list[int]
    assignment_count: int
    message: str


class AdminEstimateStatusRequest(BaseModel):
    status: EstimateStatus
    reason: str | None = Field(default=None, max_length=1000)


class AdminEstimateStatusResponse(BaseModel):
    estimate_id: int
    status: EstimateStatus
    message: str


class AdminEstimateAutoAssignRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)


class AdminEstimateAutoAssignResponse(BaseModel):
    estimate_id: int
    status: EstimateStatus
    assigned_company_ids: list[int]
    assignment_count: int
    candidate_count: int
    message: str
