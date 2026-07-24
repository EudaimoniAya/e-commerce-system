"""ordering 域订单列表/详情 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import decode_access_token
from app.ordering.schemas import OrderResponse, PaginatedOrders
from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.db.catalog import get_product_stock
from tests.support.db.ordering import backdate_order_expires_at
from tests.support.helper.auth import register_authenticated
from tests.support.helper.catalog import register_and_open_shop
from tests.support.helper.ordering import (
    arrange_purchasable_product,
    create_order,
    create_order_by_seller,
)
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_buyer_list_orders_only_own(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家 GET /orders 仅含自己的订单。"""
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

    # 独立商品，避免两买家共享库存导致隐性耦合
    other_category, other_product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=5,
    )
    assert other_product is not None
    assert other_product.status_code == 201
    assert other_product.body is not None

    other_order = await create_order(
        integration_client,
        headers=bearer_headers(other_user.body.access_token),
        items=[(other_product.body.id, 1)],
    )
    assert other_order.status_code == 201
    assert other_order.body is not None

    response: Response = await integration_client.get(
        "/orders",
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    assert body.total >= 1
    assert all(uuid.UUID(item.buyer_user_id) for item in body.items)
    assert created.body.id in {item.id for item in body.items}
    assert other_order.body.id not in {item.id for item in body.items}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shop_owner_list_me_orders(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店主 GET /shops/me/orders 仅含本店订单。"""
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

    # 建另一个店的订单，验证店主列表不会跨店泄漏
    other_reg, other_shop = await register_and_open_shop(integration_client)
    assert other_shop is not None
    assert other_shop.status_code == 201
    other_category, other_product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=other_reg.body.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=5,
    )
    assert other_product is not None
    assert other_product.status_code == 201
    assert other_product.body is not None

    other_order = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(other_product.body.id, 1)],
    )
    assert other_order.status_code == 201
    assert other_order.body is not None

    response: Response = await integration_client.get(
        "/shops/me/orders",
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    assert body.total >= 1
    assert all(item.shop_id == shop_owner.shop_id for item in body.items)
    assert created.body.id in {item.id for item in body.items}
    assert other_order.body.id not in {item.id for item in body.items}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_order_unrelated_user_returns_404(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """既非买家也非本店店主 GET /orders/{id} 返回 404。"""
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

    stranger = await register_authenticated(integration_client)
    assert stranger.status_code == 201
    assert stranger.body is not None

    response: Response = await integration_client.get(
        f"/orders/{created.body.id}",
        headers=bearer_headers(stranger.body.access_token),
    )

    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_and_get_orders_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问列表与详情返回 401。"""
    list_resp: Response = await integration_client.get("/orders")
    assert list_resp.status_code == 401

    me_orders: Response = await integration_client.get("/shops/me/orders")
    assert me_orders.status_code == 401

    detail: Response = await integration_client.get(
        "/orders/00000000-0000-0000-0000-000000000001"
    )
    assert detail.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_order_triggers_lazy_release_after_expiry(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """过期后 GET /orders/{id} 触发懒释放：cancelled/expired 且库存还原。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=9,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 4)],
    )
    assert created.status_code == 201
    assert created.body is not None

    # backdate 模拟 TTL 过期（替代 override_order_reservation_ttl + wait_past_order_expiry）
    await backdate_order_expires_at(db_session, created.body.id)

    response: Response = await integration_client.get(
        f"/orders/{created.body.id}",
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    order = OrderResponse.model_validate(response.json())
    assert order.status == "cancelled"
    assert order.cancel_reason == "expired"

    # DB 断言库存还原
    assert await get_product_stock(db_session, product.body.id) == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_buyer_list_triggers_lazy_release_after_expiry(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """过期后 GET /orders 列表触发懒释放：响应体 status=cancelled、reason=expired。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=9,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 4)],
    )
    assert created.status_code == 201
    assert created.body is not None

    # backdate 模拟 TTL 过期（替代 override_order_reservation_ttl + wait_past_order_expiry）
    await backdate_order_expires_at(db_session, created.body.id)

    response: Response = await integration_client.get(
        "/orders",
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    expired_order = next(
        (item for item in body.items if item.id == created.body.id),
        None,
    )
    assert expired_order is not None
    assert expired_order.status == "cancelled"
    assert expired_order.cancel_reason == "expired"

    # DB 断言库存还原
    assert await get_product_stock(db_session, product.body.id) == initial_stock


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shop_owner_list_triggers_lazy_release_after_expiry(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """过期后 GET /shops/me/orders 列表触发懒释放：响应体 status=cancelled、reason=expired。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=9,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 4)],
    )
    assert created.status_code == 201
    assert created.body is not None

    # backdate 模拟 TTL 过期（替代 override_order_reservation_ttl + wait_past_order_expiry）
    await backdate_order_expires_at(db_session, created.body.id)

    response: Response = await integration_client.get(
        "/shops/me/orders",
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    expired_order = next(
        (item for item in body.items if item.id == created.body.id),
        None,
    )
    assert expired_order is not None
    assert expired_order.status == "cancelled"
    assert expired_order.cancel_reason == "expired"

    # DB 断言库存还原
    assert await get_product_stock(db_session, product.body.id) == initial_stock


# ── 卖家建单可见性 ───────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seller_order_visible_to_buyer_in_list(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """卖家建单后，指定买家在 GET /orders 中可见该订单。"""
    buyer = await register_authenticated(integration_client)
    assert buyer.status_code == 201
    assert buyer.body is not None
    buyer_user_id = buyer.body.user.id

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
        buyer_user_id=str(buyer_user_id),
        items=[(product.body.id, 1)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    response: Response = await integration_client.get(
        "/orders",
        headers=bearer_headers(buyer.body.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    assert seller_order.body.id in {item.id for item in body.items}
    # 红阶段时 initiated_by 字段尚未实现，以下断言预期失败
    raw_item = next(
        (it for it in response.json()["items"] if it["id"] == seller_order.body.id),
        None,
    )
    if raw_item is not None:
        assert "initiated_by" in raw_item
        assert raw_item["initiated_by"] == "seller"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_buyer_order_initiated_by_buyer_in_list(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家建单后，GET /orders 响应行含 initiated_by=buyer。"""
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

    response: Response = await integration_client.get(
        "/orders",
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert response.status_code == 200

    # 红阶段时 initiated_by 字段尚未实现，以下断言预期失败
    raw_item = next(
        (it for it in response.json()["items"] if it["id"] == created.body.id),
        None,
    )
    if raw_item is not None:
        assert "initiated_by" in raw_item
        assert raw_item["initiated_by"] == "buyer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seller_order_lazy_release_in_buyer_list(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """过期后，卖家建单在买家 GET /orders 列表触发懒释放。"""
    buyer_user_id = decode_access_token(authenticated_user.access_token)

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=9,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None
    initial_stock = product.body.stock

    seller_order = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(buyer_user_id),
        items=[(product.body.id, 4)],
    )
    assert seller_order.status_code == 201
    assert seller_order.body is not None

    # backdate 模拟 TTL 过期（替代 override_order_reservation_ttl + wait_past_order_expiry）
    await backdate_order_expires_at(db_session, seller_order.body.id)

    response: Response = await integration_client.get(
        "/orders",
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    body = PaginatedOrders.model_validate(response.json())
    expired_order = next(
        (item for item in body.items if item.id == seller_order.body.id),
        None,
    )
    assert expired_order is not None
    assert expired_order.status == "cancelled"
    assert expired_order.cancel_reason == "expired"

    # DB 断言库存还原
    assert await get_product_stock(db_session, product.body.id) == initial_stock
