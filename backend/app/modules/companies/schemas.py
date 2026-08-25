from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class CompanyRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    owner_name: str | None = Field(default=None, min_length=2, max_length=100)
    company_name: str = Field(min_length=2, max_length=150)

    business_number: str = Field(min_length=10, max_length=50)
    representative_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    postal_code: str | None = Field(default=None, max_length=20)
    address: str | None = None
    address_detail: str | None = None
    sido: str | None = Field(default=None, max_length=50)
    sigungu: str | None = Field(default=None, max_length=50)
    eupmyeondong: str | None = Field(default=None, max_length=50)

    marketing_agreed: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls,value:str)->str:
        if not re.search(r"[A-Za-z]",value) or not re.search(r"[0-9]",value) or not re.search(r"[^A-Za-z0-9]",value): raise ValueError("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다.")
        return value

    @field_validator(
        "company_name",
        "business_number",
        "representative_name",
        "postal_code",
        "address",
        "address_detail",
        "sido",
        "sigungu",
        "eupmyeondong",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class CompanyRegisterResponse(BaseModel):
    user_id: int
    company_id: int
    email: EmailStr
    company_name: str
    user_status: str
    company_status: str
    membership_plan: str
    message: str


from datetime import datetime
from typing import Any

from pydantic import ConfigDict


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    representative_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    postal_code: str | None = Field(default=None, max_length=20)
    address: str | None = None
    address_detail: str | None = None
    sido: str | None = Field(default=None, max_length=50)
    sigungu: str | None = Field(default=None, max_length=50)
    eupmyeondong: str | None = Field(default=None, max_length=50)

    latitude: float | None = None
    longitude: float | None = None

    intro: str | None = Field(default=None, max_length=10000)
    website_url: str | None = Field(default=None, max_length=2000)
    kakao_url: str | None = Field(default=None, max_length=2000)

    consultation_available: bool | None = None
    is_visible_on_map: bool | None = None

    @field_validator(
        "name",
        "representative_name",
        "phone",
        "postal_code",
        "address",
        "address_detail",
        "sido",
        "sigungu",
        "eupmyeondong",
        "intro",
        "website_url",
        "kakao_url",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        return stripped or None


class CompanyMeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    owner_user_id: int | None
    member_role: str
    member_status: str

    name: str
    slug: str | None
    business_number: str | None
    representative_name: str | None
    phone: str | None
    email: EmailStr | None

    postal_code: str | None
    address: str | None
    address_detail: str | None
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None

    latitude: float | None
    longitude: float | None

    intro: str | None
    logo_path: str | None
    website_url: str | None
    kakao_url: str | None

    status: str
    consultation_available: bool
    is_visible_on_map: bool

    membership_plan: str | None
    membership_display_name: str | None
    membership_status: str | None
    membership_expires_at: datetime | None
    membership_features: dict[str, Any]

    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompanyServiceRegionCreateRequest(BaseModel):
    region_code: str = Field(min_length=2, max_length=30)
    sido: str = Field(min_length=1, max_length=50)
    sigungu: str | None = Field(default=None, max_length=50)
    eupmyeondong: str | None = Field(default=None, max_length=50)
    is_primary: bool = False

    @field_validator(
        "region_code",
        "sido",
        "sigungu",
        "eupmyeondong",
    )
    @classmethod
    def normalize_region_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.strip().split())
        return normalized or None


class CompanyServiceRegionResponse(BaseModel):
    id: int
    company_id: int
    region_code: str | None
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    is_primary: bool
    created_at: datetime


class CompanyServiceRegionDeleteResponse(BaseModel):
    region_id: int
    company_id: int
    message: str
