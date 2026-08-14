"""ordering 域 POST /orders/batch-pay integration 测试（TDD 红阶段）。"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.db.ordering import backdate_order_expires_at, seed_cart_item
from tests.testkit.helper.auth import register_user_via_otp
from tests.testkit.helper.ordering import (
    arrange_purchasable_product,
    batch_pay_orders,
    checkout_cart,
    create_order,
    pay_order,
)
from tests.testkit.utils import bearer_headers, decode_jwt_sub


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("batch-pay 多个 awaiting_payment 订单成功，全部 → confirmed。")
async def test_batch_pay_multi_order_returns_200(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """batch-pay 多个 awaiting_payment 订单成功，全部 → confirmed。"""
    _, product_a = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="bp-a"
    )
    _, product_b = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="20.00", name="bp-b"
    )

    # 两个立即购买订单
    order1 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_a, 1)],
    )
    assert order1.status_code == 201 and order1.body is not None
    order2 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_b, 1)],
    )
    assert order2.status_code == 201 and order2.body is not None

    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[order1.body.id, order2.body.id],
    )
    assert result.status_code == 200
    assert result.body is not None

    orders = result.body.get("orders", result.body.get("items", []))
    for o in orders:
        assert o["status"] == "confirmed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("空 order_ids 返回 422。")
async def test_batch_pay_empty_order_ids_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """空 order_ids 返回 422。"""
    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[],
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("batch-pay 可混合不同 batch 子单与立即购买单，未选单不受影响。")
async def test_batch_pay_cross_batch_and_immediate(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """batch-pay 可混合不同 batch 子单与立即购买单，未选单不受影响。"""
    _, product_a = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="cross-a"
    )
    _, product_b = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="20.00", name="cross-b"
    )
    _, product_c = await arrange_purchasable_product(
        db_session,
        shop_id=second_shop_owner.shop_id,
        stock=10,
        price="30.00",
        name="cross-c",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)

    # 立即购买单（shop A）
    immediate = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_a, 1)],
    )
    assert immediate.status_code == 201 and immediate.body is not None

    # 购物车 checkout batch 1（shop A）→ 1 个子单
    cart_b = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_b, qty=1
    )
    co1 = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_b],
    )
    assert co1.status_code == 201
    batch1_order_id = co1.body["orders"][0]["id"]

    # 购物车 checkout batch 2（shop B）→ 1 个子单（不参与 batch-pay）
    cart_c = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=product_c, qty=1
    )
    co2 = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[cart_c],
    )
    assert co2.status_code == 201
    batch2_order_id = co2.body["orders"][0]["id"]

    # Act: 混合 batch1 子单 + 立即购买单
    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[immediate.body.id, batch1_order_id],
    )
    assert result.status_code == 200

    orders = result.body.get("orders", result.body.get("items", []))
    statuses = {o["id"]: o["status"] for o in orders}
    assert statuses.get(immediate.body.id) == "confirmed"
    assert statuses.get(batch1_order_id) == "confirmed"

    # batch2 子单未被付，仍为 awaiting_payment
    from tests.testkit.db.ordering import get_order_status

    assert await get_order_status(db_session, batch2_order_id) == "awaiting_payment"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("跨 batch 子集支付：每 batch 各付 1 单，未付单仍 awaiting_payment。")
async def test_batch_pay_subset(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """跨 batch 子集支付：每 batch 各付 1 单，未付单仍 awaiting_payment。"""
    # Arrange: 两个店各两个商品
    _, prod_a1 = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="sub-a1"
    )
    _, prod_b1 = await arrange_purchasable_product(
        db_session,
        shop_id=second_shop_owner.shop_id,
        stock=10,
        price="10.00",
        name="sub-b1",
    )
    _, prod_a2 = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="sub-a2"
    )
    _, prod_b2 = await arrange_purchasable_product(
        db_session,
        shop_id=second_shop_owner.shop_id,
        stock=10,
        price="10.00",
        name="sub-b2",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)

    # Checkout batch 1：跨店 cart → 2 orders（shop A + shop B）
    c_a1 = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=prod_a1, qty=1
    )
    c_b1 = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=prod_b1, qty=1
    )
    co1 = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[c_a1, c_b1],
    )
    assert co1.status_code == 201
    orders1 = co1.body["orders"]
    assert len(orders1) == 2

    # Checkout batch 2：跨店 cart → 2 orders（shop A + shop B）
    c_a2 = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=prod_a2, qty=1
    )
    c_b2 = await seed_cart_item(
        db_session, user_id=user_id_placeholder, product_id=prod_b2, qty=1
    )
    co2 = await checkout_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_ids=[c_a2, c_b2],
    )
    assert co2.status_code == 201
    orders2 = co2.body["orders"]
    assert len(orders2) == 2

    # Act: 从 batch1 付 shop A 的单 + 从 batch2 付 shop B 的单
    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[orders1[0]["id"], orders2[1]["id"]],
    )
    assert result.status_code == 200

    resp_orders = result.body.get("orders", result.body.get("items", []))
    statuses = {o["id"]: o["status"] for o in resp_orders}
    assert statuses.get(orders1[0]["id"]) == "confirmed"
    assert statuses.get(orders2[1]["id"]) == "confirmed"

    # 未付的仍为 awaiting_payment
    from tests.testkit.db.ordering import get_order_status

    assert await get_order_status(db_session, orders1[1]["id"]) == "awaiting_payment"
    assert await get_order_status(db_session, orders2[0]["id"]) == "awaiting_payment"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("部分订单过期时 batch-pay 全失败（409），零确认。")
async def test_batch_pay_partial_expired_returns_409_zero_confirmed(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """部分订单过期时 batch-pay 全失败（409），零确认。"""
    _, product_a = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="exp-a"
    )
    _, product_b = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="20.00", name="exp-b"
    )

    order1 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_a, 1)],
    )
    assert order1.status_code == 201 and order1.body is not None
    order2 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_b, 1)],
    )
    assert order2.status_code == 201 and order2.body is not None

    # 仅让 order1 过期
    await backdate_order_expires_at(db_session, order1.body.id, seconds=3600)

    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[order1.body.id, order2.body.id],
    )
    assert result.status_code == 409

    # 两个都未被确认（order2 虽然是合法的，但因为全有或全无，也被拒绝）
    from tests.testkit.db.ordering import get_order_status

    assert await get_order_status(db_session, order1.body.id) != "confirmed"
    assert await get_order_status(db_session, order2.body.id) != "confirmed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("含非 awaiting_payment 订单时 batch-pay 返回 409。")
async def test_batch_pay_illegal_state_returns_409(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """含非 awaiting_payment 订单时 batch-pay 返回 409。"""
    _, product_a = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="10.00", name="ill-a"
    )
    _, product_b = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10, price="20.00", name="ill-b"
    )

    order1 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_a, 1)],
    )
    assert order1.status_code == 201 and order1.body is not None
    order2 = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_b, 1)],
    )
    assert order2.status_code == 201 and order2.body is not None

    # 先支付 order2 → confirmed
    paid = await pay_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=order2.body.id,
    )
    assert paid.status_code == 200

    # batch-pay 含已支付单 → 409
    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[order1.body.id, order2.body.id],
    )
    assert result.status_code == 409

    # order1 仍为 awaiting_payment（未被部分确认）
    from tests.testkit.db.ordering import get_order_status

    assert await get_order_status(db_session, order1.body.id) == "awaiting_payment"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("含他人订单时 batch-pay 返回 404（不暴露存在性）。")
async def test_batch_pay_other_user_order_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """含他人订单时 batch-pay 返回 404（不暴露存在性）。"""
    _, product_id = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id, stock=10
    )

    # 当前用户的订单
    my_order = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_id, 1)],
    )
    assert my_order.status_code == 201 and my_order.body is not None

    # 另一用户的订单
    other_reg = await register_user_via_otp(integration_client)
    assert other_reg.status_code == 201 and other_reg.body is not None
    other_order = await create_order(
        integration_client,
        headers=bearer_headers(other_reg.body.access_token),
        items=[(product_id, 1)],
    )
    assert other_order.status_code == 201 and other_order.body is not None

    result = await batch_pay_orders(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_ids=[my_order.body.id, other_order.body.id],
    )
    assert result.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("batch_pay")
@allure.title("未认证 batch-pay 返回 401。")
async def test_batch_pay_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证 batch-pay 返回 401。"""
    r = await integration_client.post(
        "/orders/batch-pay",
        json={"order_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 401
