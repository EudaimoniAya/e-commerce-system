"""ordering 域 POST /orders/{id}/pay integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.db.catalog import get_product_stock
from tests.support.db.ordering import backdate_order_expires_at, get_order_status
from tests.support.helper.auth import register_authenticated
from tests.support.helper.ordering import (
    arrange_purchasable_product,
    create_order,
    create_order_by_seller,
    pay_order,
)
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_stub_confirms_awaiting_payment(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """支付桩将 awaiting_payment 订单置为 confirmed，且不再扣库存。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 2)],
    )
    assert created.status_code == 201
    assert created.body is not None
    assert created.body.status == "awaiting_payment"

    stock_before_pay = await get_product_stock(db_session, product.body.id)
    assert stock_before_pay == 8

    paid = await pay_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=created.body.id,
    )

    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"
    assert paid.body.id == created.body.id

    assert await get_product_stock(db_session, product.body.id) == stock_before_pay


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_non_buyer_returns_403(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """非买家支付返回 403。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None

    other_user = await register_authenticated(integration_client)
    assert other_user.status_code == 201
    assert other_user.body is not None

    paid = await pay_order(
        integration_client,
        headers=bearer_headers(other_user.body.access_token),
        order_id=created.body.id,
    )

    assert paid.status_code == 403
    assert paid.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_duplicate_returns_409(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对已 confirmed 订单重复 pay 返回 409。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None

    first = await pay_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=created.body.id,
    )
    assert first.status_code == 200
    assert first.body is not None
    assert first.body.status == "confirmed"

    second = await pay_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=created.body.id,
    )

    assert second.status_code == 409
    assert second.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_unauthenticated_returns_401(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证支付返回 401。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None

    response: Response = await integration_client.post(f"/orders/{created.body.id}/pay")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_after_expiry_returns_409_and_restores_stock(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """过期后 pay 返回 409，订单 cancelled/expired，库存还原。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=7,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 3)],
    )
    assert created.status_code == 201
    assert created.body is not None

    assert await get_product_stock(db_session, product.body.id) == initial_stock - 3

    # backdate 模拟 TTL 过期（替代 override_order_reservation_ttl + wait_past_order_expiry）
    await backdate_order_expires_at(db_session, created.body.id)

    paid = await pay_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=created.body.id,
    )

    assert paid.status_code == 409
    assert paid.body is None

    # DB 断言：订单 status 与库存还原
    assert await get_order_status(db_session, created.body.id) == "cancelled"

    final_stock = await get_product_stock(db_session, product.body.id)
    assert final_stock == initial_stock


# ── 卖家发起的订单支付 ──────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_seller_initiated_by_buyer_returns_200(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """指定买家支付卖家发起的订单 → confirmed。"""
    buyer = await register_authenticated(integration_client)
    assert buyer.status_code == 201
    assert buyer.body is not None

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    seller_order = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 2)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    paid = await pay_order(
        integration_client,
        headers=bearer_headers(buyer.body.access_token),
        order_id=seller_order.body.id,
    )

    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"
    assert paid.body.id == seller_order.body.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pay_order_seller_initiated_by_shop_owner_returns_403(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主（非买家）支付卖家发起的订单 → 403。"""
    buyer = await register_authenticated(integration_client)
    assert buyer.status_code == 201
    assert buyer.body is not None

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    seller_order = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 1)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    paid = await pay_order(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=seller_order.body.id,
    )

    assert paid.status_code == 403
    assert paid.body is None
