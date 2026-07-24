"""ordering 域 HTTP helper 与跨域编排器。"""

from decimal import Decimal

from httpx import AsyncClient, Response

from app.ordering.schemas import OrderCreate, OrderResponse, ShipmentCreate
from tests.support.builders import build_order_create, unique_category_name
from tests.support.helper.catalog import create_category, create_product
from tests.support.utils import bearer_headers
from tests.support.results import (
    CategoryResult,
    OrderResult,
    ProductResult,
)


def _parse_order_body(response: Response) -> OrderResponse | None:
    """2xx 时解析 OrderResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return OrderResponse.model_validate(response.json())
    return None


async def arrange_purchasable_product(
    client: AsyncClient,
    *,
    shop_owner_token: str,
    admin_token: str,
    stock: int = 10,
    price: str | Decimal = "99.00",
    name: str | None = None,
    is_published: bool = True,
) -> tuple[CategoryResult, ProductResult | None]:
    """Arrange：为店铺创建类目 + 可购商品。

    返回 ``(CategoryResult, ProductResult)``。
    类目创建失败时 ProductResult 为 None。
    """
    category = await create_category(
        client,
        headers=bearer_headers(admin_token),
        name=unique_category_name("order"),
    )
    if category.status_code != 201 or category.body is None:
        return (category, None)

    product = await create_product(
        client,
        shop_owner_token=shop_owner_token,
        category=category,
        name=name,
        price=price,
        stock=stock,
        is_published=is_published,
    )
    return (category, product)


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
    shop_owner_token: str,
    admin_token: str,
    buyer_headers: dict[str, str],
    stock: int = 10,
    qty: int = 1,
) -> tuple[CategoryResult, ProductResult, OrderResult | None]:
    """Arrange：可购商品 → 下单 → pay → confirmed。

    返回 ``(CategoryResult, ProductResult, OrderResult)``，
    其中 OrderResult 为支付后的订单。
    任一步失败时 OrderResult 为 None；调用方在 Case 内断言。
    """
    category, product = await arrange_purchasable_product(
        client,
        shop_owner_token=shop_owner_token,
        admin_token=admin_token,
        stock=stock,
    )
    if product is None or product.status_code != 201 or product.body is None:
        return (category, product, None)

    created = await create_order(
        client,
        headers=buyer_headers,
        items=[(product.body.id, qty)],
    )
    if created.status_code != 201 or created.body is None:
        return (category, product, created)

    paid = await pay_order(
        client,
        headers=buyer_headers,
        order_id=created.body.id,
    )
    return (category, product, paid)
