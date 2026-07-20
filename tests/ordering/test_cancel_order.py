"""ordering 域 POST /orders/{id}/cancel integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ProductResponse
from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.helpers import (
    arrange_confirmed_order,
    arrange_purchasable_product,
    cancel_order,
    confirm_receipt,
    create_order,
    create_shipment,
)
from tests.support.projections import bearer_headers
from tests.support.results import OrderResult, ProductResult, RegisterResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_buyer_cancel_awaiting_payment_releases_stock(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家取消 awaiting_payment 订单：200、buyer_cancelled、库存加回。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    created = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 3)],
    )
    assert created.status_code == 201
    assert created.body is not None

    cancelled = await cancel_order(
        client,
        headers=bearer_headers(buyer),
        order_id=created.body.id,
    )

    assert cancelled.status_code == 200
    assert cancelled.body is not None
    assert cancelled.body.status == "cancelled"
    assert cancelled.body.cancel_reason == "buyer_cancelled"

    stock: Response = await client.get(f"/products/{product.body.id}")
    assert stock.status_code == 200
    assert ProductResponse.model_validate(stock.json()).stock == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seller_cancel_confirmed_releases_stock(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """卖家取消 confirmed 订单：200、seller_cancelled、库存加回。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
        stock=10,
        qty=2,
    )
    product = arranged.step(ProductResult)
    paid = arranged.step(OrderResult)
    assert product.status_code == 201
    assert product.body is not None
    assert paid.status_code == 200
    assert paid.body is not None
    initial_stock = product.request.stock

    cancelled = await cancel_order(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        order_id=paid.body.id,
    )

    assert cancelled.status_code == 200
    assert cancelled.body is not None
    assert cancelled.body.status == "cancelled"
    assert cancelled.body.cancel_reason == "seller_cancelled"

    stock: Response = await client.get(f"/products/{product.body.id}")
    assert stock.status_code == 200
    assert ProductResponse.model_validate(stock.json()).stock == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_completed_returns_409_without_stock_change(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """completed 订单禁止取消：409 且库存不变。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
        stock=10,
        qty=2,
    )
    product = arranged.step(ProductResult)
    paid = arranged.step(OrderResult)
    assert product.status_code == 201
    assert product.body is not None
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201

    completed = await confirm_receipt(
        client,
        headers=bearer_headers(buyer),
        order_id=paid.body.id,
    )
    assert completed.status_code == 200
    assert completed.body is not None
    assert completed.body.status == "completed"

    stock_before: Response = await client.get(f"/products/{product.body.id}")
    assert stock_before.status_code == 200
    stock_value = ProductResponse.model_validate(stock_before.json()).stock

    cancelled = await cancel_order(
        client,
        headers=bearer_headers(buyer),
        order_id=paid.body.id,
    )

    assert cancelled.status_code == 409
    assert cancelled.body is None

    stock_after: Response = await client.get(f"/products/{product.body.id}")
    assert stock_after.status_code == 200
    assert ProductResponse.model_validate(stock_after.json()).stock == stock_value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_order_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证取消返回 401。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None

    response: Response = await client.post(f"/orders/{created.body.id}/cancel")

    assert response.status_code == 401
