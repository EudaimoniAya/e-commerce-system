"""HTTP helper 用 ActionResult dataclass。"""

from dataclasses import dataclass

from app.catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductResponse,
    ShopCreate,
    ShopResponse,
)
from app.ordering.schemas import OrderCreate, OrderResponse
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


@dataclass
class ProductResult:
    """``POST /products`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``ProductResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        request: 本次请求发出的 ``ProductCreate`` 实例。
    """

    status_code: int
    body: ProductResponse | None
    request: ProductCreate


@dataclass
class OrderResult:
    """订单相关 HTTP 调用结果（创建 / pay 等返回订单 DTO 的端点）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``OrderResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        request: 创建订单时发出的 ``OrderCreate``；非创建类调用时为 ``None``。
    """

    status_code: int
    body: OrderResponse | None
    request: OrderCreate | None = None


@dataclass
class CartItemResult:
    """购物车行 HTTP 调用结果（POST/PATCH /cart/items 等返回 cart item 的端点）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx/201 时解析为 dict（cart item 响应）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class CartListResult:
    """GET /cart HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（含 shops/invalid_items）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class CheckoutResult:
    """POST /cart/checkout HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 201 时解析为 dict（含 checkout_batch_id/orders）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class CheckoutBatchResult:
    """GET /orders/checkout-batches/{id} HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（含 shops/paid_total/remaining_total/status）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class BatchPayResult:
    """POST /orders/batch-pay HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（含 orders 数组）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None
