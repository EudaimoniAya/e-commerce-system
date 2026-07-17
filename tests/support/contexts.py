"""Setup fixture 用 Context dataclass。"""

from dataclasses import dataclass

from app.catalog.schemas import ShopCreate, ShopResponse
from app.user.schemas import TokenResponse, UserResponse


@dataclass
class AuthContext:
    """注册用户并获取 Bearer 请求头的 Setup 上下文。"""

    status_code: int
    body: TokenResponse | None
    email: str
    password: str
    access_token: str | None
    headers: dict[str, str]
    user: UserResponse | None


@dataclass
class AdminAuthContext:
    """seed 管理员登录后的 Setup 上下文。"""

    status_code: int
    body: TokenResponse | None
    email: str
    password: str
    access_token: str | None
    headers: dict[str, str]


@dataclass
class ShopOwnerContext:
    """注册并开店成功后的 Setup 上下文。"""

    status_code: int
    body: ShopResponse | None
    auth: AuthContext
    shop: ShopResponse | None
    shop_request: ShopCreate
    headers: dict[str, str]
    email: str
    password: str
