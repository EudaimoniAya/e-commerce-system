"""Setup fixture 用 Context dataclass。"""

from dataclasses import dataclass

from app.catalog.schemas import ShopCreate, ShopResponse
from app.user.schemas import TokenResponse, UserResponse


@dataclass
class AuthContext:
    """注册用户并获取 Bearer 请求头的 Setup 上下文。

    Attributes:
        status_code: ``POST /auth/register`` 的 HTTP 状态码。
        body: 2xx 时经 ``TokenResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        email: 注册请求使用的邮箱。
        password: 注册请求使用的明文密码（仅测试上下文）。
        access_token: 注册成功时的 JWT 字符串；失败时为 ``None``。
        headers: 含 ``Authorization: Bearer …`` 的请求头；失败时为空 dict。
        user: 注册成功时 ``body.user``；失败时为 ``None``。
    """

    status_code: int
    body: TokenResponse | None
    email: str
    password: str
    access_token: str | None
    headers: dict[str, str]
    user: UserResponse | None


@dataclass
class AdminAuthContext:
    """seed 管理员登录后的 Setup 上下文。

    Attributes:
        status_code: ``POST /auth/login`` 的 HTTP 状态码。
        body: 2xx 时经 ``TokenResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        email: 管理员登录邮箱（migration seed）。
        password: 管理员登录明文密码（仅测试上下文）。
        access_token: 登录成功时的 JWT 字符串；失败时为 ``None``。
        headers: 含 ``Authorization: Bearer …`` 的请求头；失败时为空 dict。
    """

    status_code: int
    body: TokenResponse | None
    email: str
    password: str
    access_token: str | None
    headers: dict[str, str]


@dataclass
class ShopOwnerContext:
    """注册并开店成功后的 Setup 上下文。

    ``status_code`` 表示 **开店**（``POST /shops``）一步；注册步骤状态见 ``auth.status_code``。

    Attributes:
        status_code: ``POST /shops`` 的 HTTP 状态码；注册未完整成功时非 201（见 conftest 失败路径）。
        body: 2xx 开店响应经 ``ShopResponse.model_validate`` 解析的结果；与 ``shop`` 同值或均为 ``None``。
        auth: 嵌套的注册/登录步骤上下文。
        shop: 开店成功时的 ``ShopResponse``；失败时为 ``None``。
        shop_request: 本次 ``POST /shops`` 使用的 ``ShopCreate`` 请求体。
        headers: 注册成功后的 Bearer 请求头（与 ``auth.headers`` 相同）；可用于后续已认证请求。
        email: 店主注册邮箱（来自注册步骤）。
        password: 店主注册密码（仅测试上下文）。
    """

    status_code: int
    body: ShopResponse | None
    auth: AuthContext
    shop: ShopResponse | None
    shop_request: ShopCreate
    headers: dict[str, str]
    email: str
    password: str
