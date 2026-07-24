"""Setup fixture 用 Context dataclass（极薄，仅持有关键字段）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    """注册用户 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        access_token: JWT access token。
        email: 注册邮箱。
    """

    access_token: str
    email: str


@dataclass(frozen=True)
class AdminAuthContext:
    """seed 管理员登录后的 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        access_token: JWT access token。
    """

    access_token: str


@dataclass(frozen=True)
class ShopOwnerContext:
    """注册并开店成功后的 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        access_token: JWT access token（店主身份的 access token）。
        shop_id: 店铺 ID。
        email: 注册邮箱。
    """

    access_token: str
    shop_id: str
    email: str
