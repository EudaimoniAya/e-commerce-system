"""ordering 域 POST /cart/checkout integration 测试（TDD 红阶段）。"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.db.catalog import get_product_stock
from tests.testkit.db.ordering import seed_cart_item
from tests.testkit.helper.catalog import register_and_open_shop
from tests.testkit.helper.ordering import (
    arrange_purchasable_product,
    checkout_cart,
    get_cart,
)
from tests.testkit.utils import bearer_headers, decode_jwt_sub


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("跨店 checkout 成功：每店创建 1 个子订单，同属一个 checkout_batch。")
async def test_checkout_cross_shop_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """跨店 checkout 成功：每店创建 1 个子订单，同属一个 checkout_batch。"""
    _, product_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="10.00",
        name="checkout-a",
    )
    other_reg, other_shop = await register_and_open_shop(integration_client)
    assert other_shop is not None and other_shop.status_code == 201
    _, product_b = await arrange_purchasable_product(
        db_session,
        shop_id=other_shop.body.id,
        stock=10,
        price="20.00",
        name="checkout-b",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_a = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_a, qty=2
    )
    cart_b = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_b, qty=1
    )

    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_a, cart_b],
    )
    assert result.status_code == 201
    assert result.body is not None

    assert "checkout_batch_id" in result.body
    uuid.UUID(result.body["checkout_batch_id"])
    orders = result.body["orders"]
    assert len(orders) == 2

    # 所有子订单同属一个 batch
    batch_id = result.body["checkout_batch_id"]
    for o in orders:
        assert o.get("checkout_batch_id") == batch_id
        assert o["status"] == "awaiting_payment"
        assert o["initiated_by"] == "buyer"

    # 库存已扣减
    assert await get_product_stock(db_session, product_a) == 8
    assert await get_product_stock(db_session, product_b) == 9

    # cart 行已删除
    cart_after = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert cart_after.status_code == 200
    all_cart_ids = []
    for s in cart_after.body.get("shops", []):
        for item in s.get("items", []):
            all_cart_ids.append(item.get("cart_item_id"))
    for inv in cart_after.body.get("invalid_items", []):
        all_cart_ids.append(inv.get("cart_item_id"))
    assert cart_a not in all_cart_ids
    assert cart_b not in all_cart_ids


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("部分结算：仅指定 cart_item_ids 被 checkout，其余保留。")
async def test_checkout_partial_keeps_unselected_cart_items(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """部分结算：仅指定 cart_item_ids 被 checkout，其余保留。"""
    _, product_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="10.00",
    )
    _, product_b = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="20.00",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_a = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_a, qty=1
    )
    cart_b = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_b, qty=1
    )

    # 仅结算 cart_a
    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_a],
    )
    assert result.status_code == 201
    assert len(result.body["orders"]) == 1

    # cart_b 仍存在
    cart_after = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert cart_after.status_code == 200
    remaining_ids = []
    for s in cart_after.body.get("shops", []):
        for item in s.get("items", []):
            remaining_ids.append(item.get("cart_item_id"))
    assert cart_b in remaining_ids


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("空 cart_item_ids 返回 422，不创建 batch 或 orders。")
async def test_checkout_empty_cart_item_ids_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """空 cart_item_ids 返回 422，不创建 batch 或 orders。"""
    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[],
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("库存不足 checkout 失败返回 422，cart 不变。")
async def test_checkout_insufficient_stock_returns_422_cart_unchanged(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """库存不足 checkout 失败返回 422，cart 不变。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=2,
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=5
    )

    # 先确认 cart 中有此行
    before = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert before.status_code == 200
    before_count = len(before.body.get("shops", []))

    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_id],
    )
    assert result.status_code == 422
    assert result.body is None or "checkout_batch_id" not in (result.body or {})

    # cart 不变
    after = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert after.status_code == 200
    assert len(after.body.get("shops", [])) == before_count

    # 库存未扣减
    assert await get_product_stock(db_session, product_id) == 2


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("checkout 锁价：order_items.unit_price 为 checkout 时刻快照。")
async def test_checkout_price_snapshot(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """checkout 锁价：order_items.unit_price 为 checkout 时刻快照。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="50.00",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=1
    )

    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_id],
    )
    assert result.status_code == 201

    order = result.body["orders"][0]
    item = order["items"][0]
    assert item["unit_price"] == "50.00"
    assert item["product_name"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("店主 checkout 本店商品返回 403，不创建 batch 或 orders。")
async def test_checkout_self_purchase_returns_403(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 checkout 本店商品返回 403，不创建 batch 或 orders。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    # 用店主自己的 token 加购 + checkout
    user_id_placeholder = decode_jwt_sub(shop_owner.access_token)
    cart_id = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_id, qty=1
    )

    result = await checkout_cart(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        cart_item_ids=[cart_id],
    )
    assert result.status_code == 403
    assert result.body is None or "checkout_batch_id" not in (result.body or {})


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_checkout")
@allure.title("未认证 checkout 返回 401。")
async def test_checkout_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证 checkout 返回 401。"""
    r = await integration_client.post(
        "/cart/checkout",
        json={"cart_item_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 401
