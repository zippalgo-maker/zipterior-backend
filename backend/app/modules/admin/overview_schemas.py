from datetime import datetime
from pydantic import BaseModel, Field

class AdminDashboardResponse(BaseModel):
    total_users: int
    total_companies: int
    pending_companies: int
    pending_portfolios: int
    active_estimates: int
    open_comment_reports: int

class AdminUserItem(BaseModel):
    id: int
    email: str
    name: str
    nickname: str | None = None
    phone: str | None = None
    role: str
    status: str
    membership_plan: str | None = None
    membership_display_name: str | None = None
    membership_status: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    oauth_providers: list[str] = []

class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int
    offset: int

class AdminCompanyItem(BaseModel):
    id: int
    owner_user_id: int | None = None
    name: str
    business_number: str | None = None
    representative_name: str | None = None
    phone: str | None = None
    email: str | None = None
    sido: str | None = None
    sigungu: str | None = None
    status: str
    consultation_available: bool
    is_visible_on_map: bool
    has_map_coordinates: bool = True
    approved_at: datetime | None = None
    created_at: datetime
    plan_key: str = "free"
    plan_display_name: str = "일반"
    portfolio_count: int = 0
    sales_contact_count: int = 0
    last_sales_contact_at: datetime | None = None

class AdminCompanyListResponse(BaseModel):
    items: list[AdminCompanyItem]
    total: int
    limit: int
    offset: int


# 2026-08-25: 업체관리 상세보기 모달용.
class AdminCompanyPortfolioItem(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime

class AdminCompanyDetailResponse(BaseModel):
    id: int
    owner_user_id: int | None = None
    name: str
    slug: str | None = None
    business_number: str | None = None
    representative_name: str | None = None
    phone: str | None = None
    email: str | None = None
    postal_code: str | None = None
    address: str | None = None
    address_detail: str | None = None
    sido: str | None = None
    sigungu: str | None = None
    eupmyeondong: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    intro: str | None = None
    logo_path: str | None = None
    website_url: str | None = None
    kakao_url: str | None = None
    status: str
    consultation_available: bool
    is_visible_on_map: bool
    suspended_reason: str | None = None
    suspended_until: datetime | None = None
    approved_at: datetime | None = None
    approved_by: int | None = None
    created_at: datetime
    updated_at: datetime
    owner_email: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_status: str | None = None
    owner_last_login_at: datetime | None = None
    plan_key: str = "free"
    plan_display_name: str = "일반"
    membership_started_at: datetime | None = None
    membership_expires_at: datetime | None = None
    portfolio_total: int = 0
    portfolio_approved: int = 0
    portfolio_pending: int = 0
    recent_portfolios: list[AdminCompanyPortfolioItem] = []

class AdminActionLogItem(BaseModel):
    id: int
    admin_user_id: int | None = None
    action_type: str
    target_type: str | None = None
    target_id: int | None = None
    reason: str | None = None
    created_at: datetime

class AdminActionLogListResponse(BaseModel):
    items: list[AdminActionLogItem]
    total: int
    limit: int
    offset: int


# 2026-08-24: 회원 상세(로그인정보/SNS 연동 조회+해제, 세션 강제
# 로그아웃, 고아 SNS 연동 정리) -- admin-dashboard.html "상세" 스텁
# 채우기.
class AdminOAuthAccountItem(BaseModel):
    id: int
    provider: str
    provider_user_id: str
    email: str | None = None
    created_at: datetime

class AdminLoginAttemptItem(BaseModel):
    id: int
    was_successful: bool
    failure_reason: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    device_name: str | None = None
    created_at: datetime

class AdminUserDetailResponse(BaseModel):
    id: int
    email: str
    name: str
    nickname: str | None = None
    phone: str | None = None
    role: str
    status: str
    suspended_reason: str | None = None
    suspended_until: datetime | None = None
    has_password: bool
    is_placeholder_email: bool
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    oauth_accounts: list[AdminOAuthAccountItem]
    recent_login_attempts: list[AdminLoginAttemptItem]

class AdminReasonRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)

class AdminUnlinkOAuthResponse(BaseModel):
    user_id: int
    provider: str
    message: str

class AdminRevokeSessionsResponse(BaseModel):
    user_id: int
    revoked_count: int
    message: str

class OrphanedOAuthAccountItem(BaseModel):
    id: int
    user_id: int
    provider: str
    provider_user_id: str
    email: str | None = None
    created_at: datetime

class OrphanedOAuthAccountListResponse(BaseModel):
    items: list[OrphanedOAuthAccountItem]

class AdminDeleteResponse(BaseModel):
    id: int
    message: str
