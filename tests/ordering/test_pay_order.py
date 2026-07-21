"""ordering 域 POST /orders/{id}/pay integration 测试（TDD 红阶段）。"""

import asyncio

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ProductResponse
from app.ordering.schemas import OrderResponse
from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.helpers import (
    arrange_purchasable_product,
    create_order,
    create_order_by_seller,
    override_order_reservation_ttl,
    pay_order,
    register_authenticated,
)
from tests.support.projections import bearer_headers
from tests.support.results import ProductResult, RegisterResult, ShopResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_stub_confirms_awaiting_payment(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """支付桩将 awaiting_payment 订单置为 confirmed，且不再扣库存。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
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
        items=[(product.body.id, 2)],
    )
    assert created.status_code == 201
    assert created.body is not None
    assert created.body.status == "awaiting_payment"

    stock_after_create: Response = await client.get(f"/products/{product.body.id}")
    assert stock_after_create.status_code == 200
    stock_before_pay = stock_after_create.json()["stock"]
    assert stock_before_pay == 8

    paid = await pay_order(
        client,
        headers=bearer_headers(buyer),
        order_id=created.body.id,
    )

    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"
    assert paid.body.id == created.body.id

    stock_after_pay: Response = await client.get(f"/products/{product.body.id}")
    assert stock_after_pay.status_code == 200
    assert stock_after_pay.json()["stock"] == stock_before_pay


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_non_buyer_returns_403(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """非买家支付返回 403。"""
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

    other = await register_authenticated(client)
    other_user = other.step(RegisterResult)
    assert other_user.status_code == 201
    assert other_user.body is not None

    paid = await pay_order(
        client,
        headers=bearer_headers(other_user),
        order_id=created.body.id,
    )

    assert paid.status_code == 403
    assert paid.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_duplicate_returns_409(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对已 confirmed 订单重复 pay 返回 409。"""
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

    first = await pay_order(
        client,
        headers=bearer_headers(buyer),
        order_id=created.body.id,
    )
    assert first.status_code == 200
    assert first.body is not None
    assert first.body.status == "confirmed"

    second = await pay_order(
        client,
        headers=bearer_headers(buyer),
        order_id=created.body.id,
    )

    assert second.status_code == 409
    assert second.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证支付返回 401。"""
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

    response: Response = await client.post(f"/orders/{created.body.id}/pay")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_after_expiry_returns_409_and_restores_stock(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """短 TTL 过期后 pay 返回 409，订单 cancelled/expired，库存还原。"""
    override_order_reservation_ttl(2)
    try:
        buyer = authenticated_user.root.step(RegisterResult)
        assert buyer.status_code == 201

        arranged = await arrange_purchasable_product(
            client,
            shop_owner=shop_owner.root,
            admin=admin_auth_headers.root,
            stock=7,
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

        stock_reserved: Response = await client.get(f"/products/{product.body.id}")
        assert stock_reserved.status_code == 200
        assert stock_reserved.json()["stock"] == initial_stock - 3

        await asyncio.sleep(3)

        paid = await pay_order(
            client,
            headers=bearer_headers(buyer),
            order_id=created.body.id,
        )

        assert paid.status_code == 409
        assert paid.body is None

        order_get: Response = await client.get(
            f"/orders/{created.body.id}",
            headers=bearer_headers(buyer),
        )
        assert order_get.status_code == 200
        order = OrderResponse.model_validate(order_get.json())
        assert order.status == "cancelled"
        assert order.cancel_reason == "expired"

        stock_restored: Response = await client.get(f"/products/{product.body.id}")
        assert stock_restored.status_code == 200
        restored = ProductResponse.model_validate(stock_restored.json())
        assert restored.stock == initial_stock
    finally:
        override_order_reservation_ttl(86400)


# ── 卖家发起的订单支付 ──────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_seller_initiated_by_buyer_returns_200(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """指定买家支付卖家发起的订单 → confirmed。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    seller_order = await create_order_by_seller(
        client,
        headers=bearer_headers(owner),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 2)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    paid = await pay_order(
        client,
        headers=bearer_headers(buyer),
        order_id=seller_order.body.id,
    )

    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"
    assert paid.body.id == seller_order.body.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_seller_initiated_by_shop_owner_returns_403(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店主（非买家）支付卖家发起的订单 → 403。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    seller_order = await create_order_by_seller(
        client,
        headers=bearer_headers(owner),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 1)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    paid = await pay_order(
        client,
        headers=bearer_headers(owner),
        order_id=seller_order.body.id,
    )

    assert paid.status_code == 403
    assert paid.body is None
