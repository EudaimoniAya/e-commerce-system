"""ordering 域 POST /orders integration 测试（TDD 红阶段）。"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.schemas import OrderResponse
from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.db.catalog import get_product_stock
from tests.support.helper.catalog import create_product, register_and_open_shop
from tests.support.helper.ordering import arrange_purchasable_product, create_order
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_multi_item_same_shop_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """同店多行可购商品下单成功，返回 201 并扣减库存。"""
    category, product_a = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        price="10.00",
        name="order-a",
    )
    assert product_a is not None
    assert product_a.status_code == 201
    assert product_a.body is not None

    product_b = await create_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        category=category,
        name="order-b",
        price="20.00",
        stock=5,
        is_published=True,
    )
    assert product_b.status_code == 201
    assert product_b.body is not None

    result = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_a.body.id, 2), (product_b.body.id, 1)],
    )
    assert result.status_code == 201
    assert result.body is not None

    body: OrderResponse = result.body
    assert body.status == "awaiting_payment"
    assert body.shop_id == shop_owner.shop_id
    uuid.UUID(body.buyer_user_id)
    assert body.expires_at is not None
    assert len(body.items) == 2
    assert Decimal(body.total_amount) == Decimal("40.00")
    uuid.UUID(body.id)

    assert await get_product_stock(db_session, product_a.body.id) == 8
    assert await get_product_stock(db_session, product_b.body.id) == 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_cross_shop_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """跨店商品合单返回 422，且不建单、不扣库存。"""
    category_a, product_a = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product_a is not None
    assert product_a.status_code == 201
    assert product_a.body is not None
    stock_before_a = product_a.body.stock

    other_reg, other_shop = await register_and_open_shop(integration_client)
    assert other_shop is not None
    assert other_shop.status_code == 201
    category_b, product_b = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=other_reg.body.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product_b is not None
    assert product_b.status_code == 201
    assert product_b.body is not None
    stock_before_b = product_b.body.stock

    response: Response = await integration_client.post(
        "/orders",
        json={
            "items": [
                {"product_id": product_a.body.id, "qty": 1},
                {"product_id": product_b.body.id, "qty": 1},
            ]
        },
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 422
    assert "detail" in response.json()

    assert await get_product_stock(db_session, product_a.body.id) == stock_before_a
    assert await get_product_stock(db_session, product_b.body.id) == stock_before_b


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_insufficient_stock_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """任一行 qty 超过可售库存返回 422，整单不建、库存不变。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=3,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 5)],
    )

    assert result.status_code == 422
    assert result.body is None

    assert await get_product_stock(db_session, product.body.id) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_unpublished_product_returns_422(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未上架商品不可下单，返回 422。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        is_published=False,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_closed_shop_returns_422(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店铺非 active（closed）时下单返回 422。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    patch_shop: Response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch_shop.status_code == 200

    result = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_owner_self_purchase_returns_403(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主购买本店商品返回 403。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 403
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_unauthenticated_returns_401(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证下单返回 401。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await integration_client.post(
        "/orders",
        json={"items": [{"product_id": product.body.id, "qty": 1}]},
    )

    assert response.status_code == 401
