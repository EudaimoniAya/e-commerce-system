"""ordering 域 POST /orders integration 测试（TDD 红阶段）。"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response

from app.ordering.schemas import OrderResponse
from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.helpers import (
    arrange_purchasable_product,
    create_order,
    create_product,
    register_and_open_shop,
)
from tests.support.projections import bearer_headers
from tests.support.results import (
    CategoryResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_multi_item_same_shop_returns_201(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """同店多行可购商品下单成功，返回 201 并扣减库存。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        price="10.00",
        name="order-a",
    )
    product_a = arranged.step(ProductResult)
    assert product_a.status_code == 201
    assert product_a.body is not None

    category = arranged.step(CategoryResult)
    product_b = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
        name="order-b",
        price="20.00",
        stock=5,
        is_published=True,
    )
    assert product_b.status_code == 201
    assert product_b.body is not None

    result = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product_a.body.id, 2), (product_b.body.id, 1)],
    )

    assert result.status_code == 201
    assert result.body is not None
    assert buyer.body is not None
    shop = shop_owner.root.step(ShopResult)
    assert shop.body is not None
    body: OrderResponse = result.body
    assert body.status == "awaiting_payment"
    assert body.shop_id == shop.body.id
    assert body.buyer_user_id == buyer.body.user.id
    assert body.expires_at is not None
    assert len(body.items) == 2
    assert Decimal(body.total_amount) == Decimal("40.00")
    uuid.UUID(body.id)

    stock_a: Response = await client.get(f"/products/{product_a.body.id}")
    assert stock_a.status_code == 200
    assert stock_a.json()["stock"] == 8

    stock_b: Response = await client.get(f"/products/{product_b.body.id}")
    assert stock_b.status_code == 200
    assert stock_b.json()["stock"] == 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_cross_shop_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """跨店商品合单返回 422，且不建单、不扣库存。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged_a = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product_a = arranged_a.step(ProductResult)
    assert product_a.status_code == 201
    assert product_a.body is not None
    stock_before_a = product_a.body.stock

    other_shop = await register_and_open_shop(client)
    assert other_shop.step(ShopResult).status_code == 201
    arranged_b = await arrange_purchasable_product(
        client,
        shop_owner=other_shop,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product_b = arranged_b.step(ProductResult)
    assert product_b.status_code == 201
    assert product_b.body is not None
    stock_before_b = product_b.body.stock

    response: Response = await client.post(
        "/orders",
        json={
            "items": [
                {"product_id": product_a.body.id, "qty": 1},
                {"product_id": product_b.body.id, "qty": 1},
            ]
        },
        headers=bearer_headers(buyer),
    )

    assert response.status_code == 422
    assert "detail" in response.json()

    stock_a: Response = await client.get(f"/products/{product_a.body.id}")
    assert stock_a.status_code == 200
    assert stock_a.json()["stock"] == stock_before_a
    stock_b: Response = await client.get(f"/products/{product_b.body.id}")
    assert stock_b.status_code == 200
    assert stock_b.json()["stock"] == stock_before_b


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_insufficient_stock_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """任一行 qty 超过可售库存返回 422，整单不建、库存不变。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=3,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 5)],
    )

    assert result.status_code == 422
    assert result.body is None

    stock: Response = await client.get(f"/products/{product.body.id}")
    assert stock.status_code == 200
    assert stock.json()["stock"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_unpublished_product_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未上架商品不可下单，返回 422。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        is_published=False,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_closed_shop_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店铺非 active（closed）时下单返回 422。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    patch_shop: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch_shop.status_code == 200

    result = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_owner_self_purchase_returns_403(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主购买本店商品返回 403。"""
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order(
        client,
        headers=bearer_headers(owner),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 403
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证下单返回 401。"""
    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await client.post(
        "/orders",
        json={"items": [{"product_id": product.body.id, "qty": 1}]},
    )

    assert response.status_code == 401
