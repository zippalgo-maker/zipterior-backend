from datetime import datetime
import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class CustomerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    marketing_agreed: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value) or not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("비밀번호는 8자 이상이며 영문, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value=value.strip()
        if not re.fullmatch(r"[A-Za-z가-힣\s]+", value): raise ValueError("이름은 한글 또는 영문만 입력할 수 있습니다.")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None: return None
        digits=re.sub(r"\D", "", value)
        if not digits: return None
        if not re.fullmatch(r"01[016789]\d{7,8}", digits): raise ValueError("올바른 휴대폰 번호를 입력해 주세요.")
        return digits

    @field_validator("nickname")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None: return None
        return value.strip() or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    nickname: str | None
    phone: str | None
    role: str
    status: str
    marketing_agreed: bool
    email_verified_at: datetime | None
    created_at: datetime


class TokenResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=500)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=500)


class MessageResponse(BaseModel):
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=500)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=500)


class MessageResponse(BaseModel):
    message: str
