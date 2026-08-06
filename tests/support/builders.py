"""构造合法 domain request schema 的 build_* 工厂。"""

import uuid
from decimal import Decimal

from app.catalog.schemas import CategoryCreate, ProductCreate, ShopCreate
from app.ordering.schemas import OrderCreate, OrderItemCreate
from app.user.schemas import LoginRequest, SmsLoginRequest, SmsRegisterRequest, SmsSendRequest

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"


def unique_email(prefix: str = "user") -> str:
    """生成唯一测试邮箱，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def unique_phone(prefix: str = "138") -> str:
    """生成唯一测试手机号（11 位大陆手机号），避免 integration 测试互相冲突。

    使用 138xxxx 号段，后 8 位为纯数字随机（不用 uuid hex，避免 a-f 字母）。
    """
    suffix = f"{uuid.uuid4().int % 10**8:08d}"
    return f"{prefix}{suffix}"


def unique_shop_name(prefix: str = "shop") -> str:
    """生成唯一店名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def unique_category_name(prefix: str = "cat") -> str:
    """生成唯一类目名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def build_sms_send_request(
    *,
    phone: str | None = None,
) -> SmsSendRequest:
    """构造合法 SmsSendRequest。"""
    return SmsSendRequest(phone=phone or unique_phone())


def build_sms_register_request(
    *,
    phone: str | None = None,
    code: str = "123456",
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> SmsRegisterRequest:
    """构造合法 SmsRegisterRequest。"""
    return SmsRegisterRequest(
        phone=phone or unique_phone(),
        code=code,
        password=password,
        nickname=nickname,
    )


def build_sms_login_request(
    *,
    phone: str | None = None,
    code: str = "123456",
) -> SmsLoginRequest:
    """构造合法 SmsLoginRequest（已有用户 OTP 登录）。"""
    return SmsLoginRequest(
        phone=phone or unique_phone(),
        code=code,
    )


def build_login_request(
    *,
    identifier: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginRequest:
    """构造合法 LoginRequest（identifier 为规范化手机号）。"""
    return LoginRequest(identifier=identifier, password=password)


def build_shop_create(
    *,
    name: str | None = None,
    description: str | None = None,
    logo_media_id: str | None = None,
) -> ShopCreate:
    """构造合法 ShopCreate。"""
    return ShopCreate(
        name=name or unique_shop_name(),
        description=description,
        logo_media_id=logo_media_id,
    )


def build_category_create(
    *,
    name: str | None = None,
    parent_id: str | None = None,
) -> CategoryCreate:
    """构造合法 CategoryCreate。"""
    return CategoryCreate(
        name=name or unique_category_name(),
        parent_id=parent_id,
    )


def build_product_create(
    *,
    name: str | None = None,
    price: str | Decimal = "99.00",
    stock: int = 10,
    description: str | None = None,
    primary_media_id: str | None = None,
    is_published: bool = False,
    category_ids: list[str],
    primary_category_id: str,
) -> ProductCreate:
    """构造合法 ProductCreate。"""
    return ProductCreate(
        name=name or f"product-{uuid.uuid4().hex[:12]}",
        price=Decimal(str(price)),
        stock=stock,
        description=description,
        primary_media_id=primary_media_id,
        is_published=is_published,
        category_ids=category_ids,
        primary_category_id=primary_category_id,
    )


# ── 兼容包装（过渡期，待 §6.2 全量迁移后移除） ─────────────────────


def build_register_request(
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> "RegisterRequestCompat":
    """[Deprecated] 构造兼容旧 RegisterRequest 的对象。

    .. deprecated::
        ``RegisterRequest`` 已随 email 注册路径移除。此包装返回兼容对象
        以确保旧测试可 import 和调用，但 ``/auth/register`` 端点已移除（404）。
    """
    return RegisterRequestCompat(
        email=email or unique_email(),
        password=password,
        nickname=nickname,
    )


class RegisterRequestCompat:
    """``build_register_request`` 返回兼容对象的过渡包装。

    提供 ``model_dump`` 方法供旧测试 ``.model_dump(mode="json")`` 调用。
    """

    def __init__(self, email: str, password: str, nickname: str | None) -> None:
        self.email = email
        self.password = password
        self.nickname = nickname

    def model_dump(self, mode: str = "python") -> dict:
        return {
            "email": self.email,
            "password": self.password,
            "nickname": self.nickname,
        }


def build_order_create(
    *,
    items: list[tuple[str, int]] | list[OrderItemCreate],
) -> OrderCreate:
    """构造合法 OrderCreate。

    ``items`` 可为 ``(product_id, qty)`` 元组列表，或已构造的 ``OrderItemCreate`` 列表。
    """
    order_items: list[OrderItemCreate] = []
    for item in items:
        if isinstance(item, OrderItemCreate):
            order_items.append(item)
        else:
            product_id, qty = item
            order_items.append(OrderItemCreate(product_id=product_id, qty=qty))
    return OrderCreate(items=order_items)
