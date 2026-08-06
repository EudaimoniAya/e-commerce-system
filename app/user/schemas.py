"""user 域请求/响应 DTO。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── 请求 DTO ────────────────────────────────────────────────────


class SmsSendRequest(BaseModel):
    """``POST /auth/sms/send`` 请求体。"""

    phone: str


class SmsRegisterRequest(BaseModel):
    """``POST /auth/sms/register`` 请求体（新用户：手机 + 验证码 + 密码）。"""

    phone: str
    code: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=8, max_length=32)
    nickname: str | None = None


class SmsLoginRequest(BaseModel):
    """``POST /auth/sms/login`` 请求体（已有用户 OTP 登录，不含 password）。"""

    phone: str
    code: str = Field(min_length=6, max_length=6)


class LoginRequest(BaseModel):
    """``POST /auth/login`` 请求体（手机号 + 密码）。

    旧版 email 登录已移除；``identifier`` 当前仅接受规范化后的大陆手机号。
    """

    identifier: str
    password: str = Field(min_length=8, max_length=32)


class UserProfileUpdateRequest(BaseModel):
    """``PATCH /users/me`` 请求体（资料字段更新）。"""

    email: EmailStr | None = None
    nickname: str | None = None
    avatar_media_id: str | None = None


# ── 响应 DTO ────────────────────────────────────────────────────


class UserResponse(BaseModel):
    """对外用户资料（不含密码字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    phone: str
    email: str | None = None
    nickname: str
    avatar_url: str | None = None
    created_at: datetime


class UserSummary(BaseModel):
    """跨域只读用户摘要（不含 email）。"""

    id: str
    nickname: str


class TokenResponse(BaseModel):
    """登录/注册成功响应。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
