"""HTTP helper 用 ActionResult dataclass。"""

from dataclasses import dataclass

from app.catalog.schemas import CategoryCreate, CategoryResponse, ShopCreate, ShopResponse
from app.user.schemas import TokenResponse


@dataclass
class RegisterResult:
    """``POST /auth/register`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``TokenResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        email: 本次注册请求使用的邮箱。
        password: 本次注册请求使用的明文密码（仅测试上下文，非 API 响应字段）。
    """

    status_code: int
    body: TokenResponse | None
    email: str
    password: str


@dataclass
class LoginResult:
    """``POST /auth/login`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``TokenResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        email: 本次登录请求使用的邮箱。
        password: 本次登录请求使用的明文密码（仅测试上下文，非 API 响应字段）。
    """

    status_code: int
    body: TokenResponse | None
    email: str
    password: str


@dataclass
class ShopResult:
    """``POST /shops`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``ShopResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        request: 本次请求发出的 ``ShopCreate`` 实例。
    """

    status_code: int
    body: ShopResponse | None
    request: ShopCreate


@dataclass
class CategoryResult:
    """``POST /categories`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``CategoryResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        request: 本次请求发出的 ``CategoryCreate`` 实例。
    """

    status_code: int
    body: CategoryResponse | None
    request: CategoryCreate
