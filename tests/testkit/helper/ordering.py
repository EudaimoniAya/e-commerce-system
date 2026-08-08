"""ordering 域 HTTP helper 与跨域编排器。"""

from decimal import Decimal

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.schemas import OrderCreate, OrderResponse, ShipmentCreate
from tests.support.builders import build_order_create, unique_category_name
from tests.support.db.catalog import seed_category, seed_product, seed_product_category
from tests.support.results import (
    BatchPayResult,
    CartItemResult,
    CartListResult,
    CheckoutBatchResult,
    CheckoutResult,
    OrderResult,
)


def _parse_order_body(response: Response) -> OrderResponse | None:
    """2xx 时解析 OrderResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return OrderResponse.model_validate(response.json())
    return None


async def arrange_purchasable_product(
    db_session: AsyncSession,
    *,
    shop_id: str,
    stock: int = 10,
    price: str | Decimal = "99.00",
    name: str | None = None,
    is_published: bool = True,
) -> tuple[str, str]:
    """Arrange（DB seed）：为店铺创建类目 + 可购商品。

    不经 HTTP，直写 SAVEPOINT session。返回 ``(category_id, product_id)``。
    """
    category_id = await seed_category(
        db_session,
        name=unique_category_name("order"),
    )
    product_name = name if name is not None else "product-" + category_id[:8]
    product_id = await seed_product(
        db_session,
        shop_id=shop_id,
        name=product_name,
        price=str(price),
        stock=stock,
        is_published=is_published,
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )
    return (category_id, product_id)


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
    db_session: AsyncSession,
    integration_client: AsyncClient,
    *,
    shop_id: str,
    buyer_headers: dict[str, str],
    stock: int = 10,
    qty: int = 1,
) -> tuple[str, str, OrderResult | None]:
    """Arrange：DB seed 类目+商品 → HTTP 下单 → HTTP pay → confirmed。

    返回 ``(category_id, product_id, OrderResult)``，
    其中 OrderResult 为支付后的订单。
    任一步失败时 OrderResult 为 None；调用方在 Case 内断言。
    """
    category_id, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_id,
        stock=stock,
    )

    created = await create_order(
        integration_client,
        headers=buyer_headers,
        items=[(product_id, qty)],
    )
    if created.status_code != 201 or created.body is None:
        return (category_id, product_id, created)

    paid = await pay_order(
        integration_client,
        headers=buyer_headers,
        order_id=created.body.id,
    )
    return (category_id, product_id, paid)


# ── Cart HTTP helpers ──────────────────────────────────────────


async def add_cart_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_id: str,
    qty: int = 1,
) -> CartItemResult:
    """调用 POST /cart/items，返回 CartItemResult（不 assert 成功状态码）。"""
    response: Response = await client.post(
        "/cart/items",
        json={"product_id": product_id, "qty": qty},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return CartItemResult(status_code=response.status_code, body=body)


async def patch_cart_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    cart_item_id: str,
    qty: int,
) -> CartItemResult:
    """调用 PATCH /cart/items/{id}，返回 CartItemResult（不 assert 成功状态码）。"""
    response: Response = await client.patch(
        f"/cart/items/{cart_item_id}",
        json={"qty": qty},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return CartItemResult(status_code=response.status_code, body=body)


async def delete_cart_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    cart_item_id: str,
) -> CartItemResult:
    """调用 DELETE /cart/items/{id}，返回 CartItemResult（status_code 204 时 body 为 None）。"""
    response: Response = await client.delete(
        f"/cart/items/{cart_item_id}",
        headers=headers,
    )
    return CartItemResult(status_code=response.status_code, body=None)


async def get_cart(
    client: AsyncClient,
    *,
    headers: dict[str, str],
) -> CartListResult:
    """调用 GET /cart，返回 CartListResult（不 assert 成功状态码）。"""
    response: Response = await client.get(
        "/cart",
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return CartListResult(status_code=response.status_code, body=body)


async def checkout_cart(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    cart_item_ids: list[str],
) -> CheckoutResult:
    """调用 POST /cart/checkout，返回 CheckoutResult（不 assert 成功状态码）。"""
    response: Response = await client.post(
        "/cart/checkout",
        json={"cart_item_ids": cart_item_ids},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return CheckoutResult(status_code=response.status_code, body=body)


async def get_checkout_batch(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    batch_id: str,
) -> CheckoutBatchResult:
    """调用 GET /orders/checkout-batches/{id}，返回 CheckoutBatchResult（不 assert 成功状态码）。"""
    response: Response = await client.get(
        f"/orders/checkout-batches/{batch_id}",
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return CheckoutBatchResult(status_code=response.status_code, body=body)


async def batch_pay_orders(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    order_ids: list[str],
) -> BatchPayResult:
    """调用 POST /orders/batch-pay，返回 BatchPayResult（不 assert 成功状态码）。"""
    response: Response = await client.post(
        "/orders/batch-pay",
        json={"order_ids": order_ids},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return BatchPayResult(status_code=response.status_code, body=body)
