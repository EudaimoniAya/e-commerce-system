"""user 域请求/响应 DTO。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """注册请求体。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=32)
    nickname: str | None = None


class LoginRequest(BaseModel):
    """登录请求体。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=32)


class UserResponse(BaseModel):
    """对外用户资料（不含密码字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    nickname: str
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
