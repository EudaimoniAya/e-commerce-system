"""ordering 域 POST /orders/{id}/cancel integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.db.catalog import get_product_stock
from tests.support.helper.ordering import (
    arrange_confirmed_order,
    arrange_purchasable_product,
    cancel_order,
    confirm_receipt,
    create_order,
    create_shipment,
)
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_buyer_cancel_awaiting_payment_releases_stock(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家取消 awaiting_payment 订单：200、buyer_cancelled、库存加回。"""
    category_id, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    initial_stock = 10

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_id, 3)],
    )
    assert created.status_code == 201
    assert created.body is not None

    cancelled = await cancel_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=created.body.id,
    )

    assert cancelled.status_code == 200
    assert cancelled.body is not None
    assert cancelled.body.status == "cancelled"
    assert cancelled.body.cancel_reason == "buyer_cancelled"

    assert await get_product_stock(db_session, product_id) == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seller_cancel_confirmed_releases_stock(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """卖家取消 confirmed 订单：200、seller_cancelled、库存加回。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        stock=10,
        qty=2,
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None
    initial_stock = 10

    cancelled = await cancel_order(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=paid.body.id,
    )

    assert cancelled.status_code == 200
    assert cancelled.body is not None
    assert cancelled.body.status == "cancelled"
    assert cancelled.body.cancel_reason == "seller_cancelled"

    assert await get_product_stock(db_session, product_id) == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_completed_returns_409_without_stock_change(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """completed 订单禁止取消：409 且库存不变。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        stock=10,
        qty=2,
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201

    completed = await confirm_receipt(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=paid.body.id,
    )
    assert completed.status_code == 200
    assert completed.body is not None
    assert completed.body.status == "completed"

    stock_before = await get_product_stock(db_session, product_id)

    cancelled = await cancel_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=paid.body.id,
    )

    assert cancelled.status_code == 409
    assert cancelled.body is None

    assert await get_product_stock(db_session, product_id) == stock_before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_order_unauthenticated_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证取消返回 401。"""
    category_id, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None

    response: Response = await integration_client.post(f"/orders/{created.body.id}/cancel")

    assert response.status_code == 401
