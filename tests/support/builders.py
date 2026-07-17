"""构造合法 domain request schema 的 build_* 工厂。"""

import uuid
from decimal import Decimal

from app.catalog.schemas import CategoryCreate, ProductCreate, ShopCreate
from app.user.schemas import LoginRequest, RegisterRequest

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"


def unique_email(prefix: str = "user") -> str:
    """生成唯一测试邮箱，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def unique_shop_name(prefix: str = "shop") -> str:
    """生成唯一店名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def unique_category_name(prefix: str = "cat") -> str:
    """生成唯一类目名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def build_register_request(
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> RegisterRequest:
    """构造合法 RegisterRequest。"""
    return RegisterRequest(
        email=email or unique_email(),
        password=password,
        nickname=nickname,
    )


def build_login_request(
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginRequest:
    """构造合法 LoginRequest。"""
    return LoginRequest(email=email, password=password)


def build_shop_create(
    *,
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> ShopCreate:
    """构造合法 ShopCreate。"""
    return ShopCreate(
        name=name or unique_shop_name(),
        description=description,
        logo_url=logo_url,
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
    image_url: str | None = None,
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
        image_url=image_url,
        is_published=is_published,
        category_ids=category_ids,
        primary_category_id=primary_category_id,
    )
