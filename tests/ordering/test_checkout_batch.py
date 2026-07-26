"""ordering 域 GET /orders/checkout-batches/{id} integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.ordering import backdate_order_expires_at, seed_cart_item, seed_order
from tests.support.helper.auth import register_user
from tests.support.helper.catalog import register_and_open_shop
from tests.support.helper.ordering import (
    arrange_purchasable_product,
    checkout_cart,
    get_checkout_batch,
    pay_order,
)
from tests.support.utils import bearer_headers, decode_jwt_sub


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_checkout_batch_returns_hierarchy_and_totals(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家查看本人 checkout_batch：含 shops、totals、derived status。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="30.00",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=2
    )

    checkout = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_id],
    )
    assert checkout.status_code == 201
    batch_id = checkout.body["checkout_batch_id"]

    result = await get_checkout_batch(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        batch_id=batch_id,
    )
    assert result.status_code == 200
    assert result.body is not None

    assert result.body["id"] == batch_id
    assert result.body["buyer_user_id"] is not None
    assert "shops" in result.body
    assert "paid_total" in result.body
    assert "remaining_total" in result.body
    assert "status" in result.body

    # remaining_total 为 awaiting_payment 子单 total_amount 之和
    assert result.body["remaining_total"] == "60.00"
    assert result.body["paid_total"] == "0.00"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_checkout_batch_other_user_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """非本人查看 checkout_batch 返回 404。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=1
    )

    checkout = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_id],
    )
    assert checkout.status_code == 201
    batch_id = checkout.body["checkout_batch_id"]

    # 另一个用户尝试查看
    other_reg = await register_user(integration_client)
    assert other_reg.status_code == 201 and other_reg.body is not None

    result = await get_checkout_batch(
        integration_client,
        headers=bearer_headers(other_reg.body.access_token),
        batch_id=batch_id,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_checkout_batch_with_cancelled_order(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """batch 含 cancelled 子单时 remaining_total 仅计 awaiting_payment 子单。"""
    # 两个商品分别 checkout 到两个子订单
    _, product_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="10.00",
        name="batch-cancel-a",
    )
    _, product_b = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="20.00",
        name="batch-cancel-b",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_a = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_a, qty=1
    )
    cart_b = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_b, qty=1
    )

    checkout = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_a, cart_b],
    )
    assert checkout.status_code == 201
    batch_id = checkout.body["checkout_batch_id"]
    orders = checkout.body["orders"]

    # 取消第一个子订单
    from tests.support.helper.ordering import cancel_order

    cancel_result = await cancel_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=orders[0]["id"],
    )
    assert cancel_result.status_code == 200

    result = await get_checkout_batch(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        batch_id=batch_id,
    )
    assert result.status_code == 200

    # remaining_total 仅含仍 awaiting_payment 的单
    assert result.body["remaining_total"] == "20.00"

    # 各子单展示真实 status
    order_statuses = []
    for s in result.body.get("shops", []):
        for o in s.get("orders", []):
            order_statuses.append(o["status"])
    assert "cancelled" in order_statuses


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_checkout_batch_lazy_release(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """GET batch 时对过期 awaiting_payment 子单触发懒释放。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=5,
        price="25.00",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=1
    )

    checkout = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_id],
    )
    assert checkout.status_code == 201
    batch_id = checkout.body["checkout_batch_id"]
    order_id = checkout.body["orders"][0]["id"]

    # 回拨过期
    await backdate_order_expires_at(db_session, order_id, seconds=3600)

    result = await get_checkout_batch(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        batch_id=batch_id,
    )
    assert result.status_code == 200

    # 子单应为 cancelled
    order_statuses = []
    for s in result.body.get("shops", []):
        for o in s.get("orders", []):
            order_statuses.append(o["status"])
    assert "cancelled" in order_statuses

    # remaining_total 应为 0（全部已终态）
    assert result.body["remaining_total"] == "0.00"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_checkout_batch_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 GET /orders/checkout-batches/{id} 返回 401。"""
    r = await integration_client.get(f"/orders/checkout-batches/{str(uuid.uuid4())}")
    assert r.status_code == 401
