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
class SmsSendResult:
    """``POST /auth/sms/send`` 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        phone: 本次请求使用的规范化手机号。
    """

    status_code: int
    phone: str


@dataclass
class SmsRegisterResult:
    """``POST /auth/sms/register`` 调用结果。"""

    status_code: int
    body: TokenResponse | None
    phone: str
    password: str


@dataclass
class SmsLoginResult:
    """``POST /auth/sms/login`` 调用结果（OTP 登录，非密码登录）。"""

    status_code: int
    body: TokenResponse | None
    phone: str


@dataclass
class LoginResult:
    """``POST /auth/login``（手机号 + 密码）调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时经 ``TokenResponse.model_validate`` 解析的响应体；非 2xx 时为 ``None``。
        identifier: 本次登录请求使用的标识符（规范化手机号）。
        password: 本次登录请求使用的明文密码（仅测试上下文，非 API 响应字段）。
    """

    status_code: int
    body: TokenResponse | None
    identifier: str
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


@dataclass
class FavoriteResult:
    """收藏 HTTP 调用结果（POST/DELETE /favorites*）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: POST 2xx 时解析为 dict（含 id/product_id/created_at）；DELETE 204 及非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class FavoriteListResult:
    """GET /favorites HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（items/unavailable_items/total/limit/offset）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class BatchDeleteFavoritesResult:
    """POST /favorites/batch-delete HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（含 deleted_count）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class BrowseAcceptedResult:
    """浏览 HTTP 调用结果（POST /browse、DELETE /browse/{product_id}）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: POST 2xx 时解析为 dict（含 ``accepted``）；DELETE 204 及非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class BrowseListResult:
    """GET /browse HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（items/unavailable_items/total/limit/offset）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class ConversationResult:
    """support 会话 HTTP 调用结果（GET 买家会话 / GET inbox 详情 / PATCH 买家模式）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx/200 时解析为 dict（含 id/shop_id/buyer_user_id/handler_mode/updated_at/last_message_preview）；
              非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class MessageResult:
    """support 发消息 HTTP 调用结果（买家 POST / 店主 POST）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx/201 时解析为 dict（含 id/conversation_id/sender_role/author_role/body/message_refs/created_at）；
              非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class MessageListResult:
    """support 消息列表 HTTP 调用结果（GET 买家 messages / GET inbox messages）。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（items/total/limit/offset，符合 infra-pagination）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class InboxListResult:
    """GET /support/inbox HTTP 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx 时解析为 dict（items/total/limit/offset，items 含 last_message_preview）；非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None


@dataclass
class MediaResult:
    """POST /media 调用结果。

    Attributes:
        status_code: HTTP 响应状态码。
        body: 2xx/201 时解析为 dict（含 id/url/content_type/size_bytes/created_at）；
              非成功时为 ``None``。
    """

    status_code: int
    body: dict | None = None
