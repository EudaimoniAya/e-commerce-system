"""integration 测试 HTTP helper 与 orchestrator。"""

import uuid
from decimal import Decimal

from httpx import AsyncClient, Response

from app.catalog.schemas import CategoryResponse, ProductResponse, ShopResponse
from app.ordering.schemas import OrderCreate, OrderResponse, ShipmentCreate
from app.user.schemas import TokenResponse
from tests.support.builders import (
    build_category_create,
    build_login_request,
    build_order_create,
    build_product_create,
    build_register_request,
    build_shop_create,
    unique_category_name,
)
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import (
    CategoryResult,
    LoginResult,
    OrderResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PASSWORD = "1919810810"


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


def _parse_token_body(response: Response) -> TokenResponse | None:
    """2xx 时解析 TokenResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return TokenResponse.model_validate(response.json())
    return None


def _parse_shop_body(response: Response) -> ShopResponse | None:
    """2xx 时解析 ShopResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return ShopResponse.model_validate(response.json())
    return None


def _parse_category_body(response: Response) -> CategoryResponse | None:
    """2xx 时解析 CategoryResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return CategoryResponse.model_validate(response.json())
    return None


def _parse_product_body(response: Response) -> ProductResponse | None:
    """2xx 时解析 ProductResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return ProductResponse.model_validate(response.json())
    return None


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> RegisterResult:
    """调用 POST /auth/register，返回 RegisterResult。"""
    request = build_register_request(
        email=email,
        password=password,
        nickname=nickname,
    )
    response: Response = await client.post(
        "/auth/register",
        json=request.model_dump(mode="json"),
    )
    return RegisterResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginResult:
    """调用 POST /auth/login，返回 LoginResult。"""
    request = build_login_request(email=email, password=password)
    response: Response = await client.post(
        "/auth/login",
        json=request.model_dump(mode="json"),
    )
    return LoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_admin(client: AsyncClient) -> PipelineResult:
    """使用 migration seed 管理员登录，返回 ``PipelineResult(steps=(LoginResult,))``。"""
    logged_in = await login_user(
        client,
        email=_ADMIN_SEED_EMAIL,
        password=_ADMIN_SEED_PASSWORD,
    )
    return PipelineResult(steps=(logged_in,))


async def register_authenticated(client: AsyncClient) -> PipelineResult:
    """注册用户，返回 ``PipelineResult(steps=(RegisterResult,))``。"""
    registered = await register_user(client)
    return PipelineResult(steps=(registered,))


async def create_shop(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> ShopResult:
    """调用 POST /shops，返回 ShopResult。"""
    request = build_shop_create(
        name=name,
        description=description,
        logo_url=logo_url,
    )
    response: Response = await client.post(
        "/shops",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return ShopResult(
        status_code=response.status_code,
        body=_parse_shop_body(response),
        request=request,
    )


async def register_and_open_shop(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    shop_name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> PipelineResult:
    """注册用户并调用 POST /shops，返回 ``PipelineResult``。

    注册失败时 steps 仅含 ``RegisterResult``；成功开店后为
    ``(RegisterResult, ShopResult)``。
    """
    registered: RegisterResult = await register_user(
        client, email=email, password=password
    )

    if registered.status_code != 201 or registered.body is None:
        return PipelineResult(steps=(registered,))

    shop_result: ShopResult = await create_shop(
        client,
        headers=bearer_headers(registered),
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )
    return PipelineResult(steps=(registered, shop_result))


async def create_category(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    parent_id: str | None = None,
) -> CategoryResult:
    """调用 POST /categories，返回 CategoryResult。"""
    request = build_category_create(name=name, parent_id=parent_id)
    response: Response = await client.post(
        "/categories",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return CategoryResult(
        status_code=response.status_code,
        body=_parse_category_body(response),
        request=request,
    )


async def create_product(
    client: AsyncClient,
    *,
    shop_owner: PipelineResult,
    category: CategoryResult,
    name: str | None = None,
    price: str | Decimal = "99.00",
    stock: int = 10,
    description: str | None = None,
    image_url: str | None = None,
    is_published: bool = False,
) -> ProductResult:
    """调用 POST /products，返回 ProductResult（不 assert 成功状态码）。

    扇入前置 ``shop_owner`` / ``category`` 须由 Case 或 fixture 持有；
    ``category.body`` 为 None 时使用占位 UUID，由 API 如实返回错误。
    """
    category_id = (
        category.body.id if category.body is not None else str(uuid.uuid4())
    )
    request = build_product_create(
        name=name,
        price=price,
        stock=stock,
        description=description,
        image_url=image_url,
        is_published=is_published,
        category_ids=[category_id],
        primary_category_id=category_id,
    )
    response: Response = await client.post(
        "/products",
        json=request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner.step(RegisterResult)),
    )
    return ProductResult(
        status_code=response.status_code,
        body=_parse_product_body(response),
        request=request,
    )


def _parse_order_body(response: Response) -> OrderResponse | None:
    """2xx 时解析 OrderResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return OrderResponse.model_validate(response.json())
    return None


async def arrange_purchasable_product(
    client: AsyncClient,
    *,
    shop_owner: PipelineResult,
    admin: PipelineResult,
    stock: int = 10,
    price: str | Decimal = "99.00",
    name: str | None = None,
    is_published: bool = True,
) -> PipelineResult:
    """Arrange：为店铺创建类目 + 可购商品。

    返回 ``PipelineResult(steps=(CategoryResult, ProductResult))``。
    扇入前置 ``shop_owner`` / ``admin`` 须由 Case 或 fixture 持有。
    类目创建失败时提前返回 ``PipelineResult(steps=(CategoryResult,))``。
    """
    category = await create_category(
        client,
        headers=bearer_headers(admin.step(LoginResult)),
        name=unique_category_name("order"),
    )
    if category.status_code != 201 or category.body is None:
        return PipelineResult(steps=(category,))

    product = await create_product(
        client,
        shop_owner=shop_owner,
        category=category,
        name=name,
        price=price,
        stock=stock,
        is_published=is_published,
    )
    return PipelineResult(steps=(category, product))


async def create_order_by_seller(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    buyer_user_id: str,
    items: list[tuple[str, int]],
) -> OrderResult:
    """调用 POST /shops/me/orders，返回 OrderResult（不 assert 成功状态码）。

    body 格式：``{"buyer_user_id": "<uuid>", "items": [{"product_id", "qty"}, ...]}``。
    """
    payload: dict[str, object] = {
        "buyer_user_id": buyer_user_id,
        "items": [{"product_id": pid, "qty": qty} for pid, qty in items],
    }
    response: Response = await client.post(
        "/shops/me/orders",
        json=payload,
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=None,
    )


async def create_order(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    items: list[tuple[str, int]] | OrderCreate,
) -> OrderResult:
    """调用 POST /orders，返回 OrderResult（不 assert 成功状态码）。"""
    request = (
        items if isinstance(items, OrderCreate) else build_order_create(items=items)
    )
    response: Response = await client.post(
        "/orders",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=request,
    )


async def pay_order(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    order_id: str,
) -> OrderResult:
    """调用 POST /orders/{id}/pay，返回 OrderResult（不 assert 成功状态码）。"""
    response: Response = await client.post(
        f"/orders/{order_id}/pay",
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=None,
    )


async def create_shipment(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    order_id: str,
    note: str | None = None,
) -> OrderResult:
    """调用 POST /orders/{id}/shipments，返回 OrderResult（不 assert 成功状态码）。"""
    request = ShipmentCreate(note=note)
    response: Response = await client.post(
        f"/orders/{order_id}/shipments",
        json=request.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=None,
    )


async def confirm_receipt(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    order_id: str,
) -> OrderResult:
    """调用 POST /orders/{id}/confirm-receipt，返回 OrderResult。"""
    response: Response = await client.post(
        f"/orders/{order_id}/confirm-receipt",
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=None,
    )


async def cancel_order(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    order_id: str,
) -> OrderResult:
    """调用 POST /orders/{id}/cancel，返回 OrderResult（不 assert 成功状态码）。"""
    response: Response = await client.post(
        f"/orders/{order_id}/cancel",
        headers=headers,
    )
    return OrderResult(
        status_code=response.status_code,
        body=_parse_order_body(response),
        request=None,
    )


async def arrange_confirmed_order(
    client: AsyncClient,
    *,
    shop_owner: PipelineResult,
    admin: PipelineResult,
    buyer_headers: dict[str, str],
    stock: int = 10,
    qty: int = 1,
) -> PipelineResult:
    """Arrange：可购商品 → 下单 → pay → confirmed。

    返回 ``PipelineResult(steps=(CategoryResult, ProductResult, OrderResult))``，
    其中最后一步 ``OrderResult`` 为支付后的订单（``status=confirmed`` 时 body 可用）。
    任一步失败时仍如实返回已有 steps（不 assert）；调用方在 Case 内断言。
    """
    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner,
        admin=admin,
        stock=stock,
    )
    category = arranged.step(CategoryResult)
    product = arranged.step(ProductResult)
    if product.status_code != 201 or product.body is None:
        return PipelineResult(steps=(category, product))

    created = await create_order(
        client,
        headers=buyer_headers,
        items=[(product.body.id, qty)],
    )
    if created.status_code != 201 or created.body is None:
        return PipelineResult(steps=(category, product, created))

    paid = await pay_order(
        client,
        headers=buyer_headers,
        order_id=created.body.id,
    )
    return PipelineResult(steps=(category, product, paid))
