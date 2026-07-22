"""ordering 域 POST /shops/me/orders integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/ordering-seller-orders/spec.md）：
- 卖家建单成功 → 201 + initiated_by=seller
- 指定买家不存在 → 404
- 指定买家已禁用 → 422
- 卖家指定本人为买家 → 403
- 非本店商品 → 422
- 店铺 closed → 422
- 未认证 → 401
- 无店铺 → 404
"""

import uuid

import pytest
from httpx import AsyncClient, Response

from tests.support.builders import unique_email, unique_category_name
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.helpers import (
    arrange_purchasable_product,
    create_category,
    create_order_by_seller,
    create_product,
    register_and_open_shop,
)
from tests.support.projections import bearer_headers
from tests.support.results import (
    LoginResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)
from tests.support.seeds import seed_inactive_user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_returns_201(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店主为本店已上架且库存充足的商品为另一有效用户建单成功，返回 201 + initiated_by=seller。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        price="49.99",
        name="seller-order-a",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order_by_seller(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 2)],
    )

    assert result.status_code == 201
    assert result.body is not None
    assert result.body.status == "awaiting_payment"
    assert result.body.buyer_user_id == str(buyer.body.user.id)
    assert result.body.shop_id == str(shop_owner.root.step(ShopResult).body.id)

    # 响应体应暴露 initiated_by=seller（实现后覆盖）
    # assert result.body.initiated_by == "seller"

    # 库存已扣减
    stock: Response = await client.get(f"/products/{product.body.id}")
    assert stock.status_code == 200
    assert stock.json()["stock"] == 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_buyer_not_found_returns_404(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """指定买家在 users 表中不存在返回 404。"""
    assert shop_owner.root.step(ShopResult).status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-404",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    non_existent_id = str(uuid.uuid4())
    result = await create_order_by_seller(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        buyer_user_id=non_existent_id,
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 404
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_disabled_buyer_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    database_url: str,
) -> None:
    """指定买家 is_active=false 返回 422。"""
    assert shop_owner.root.step(ShopResult).status_code == 201

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-disabled",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    disabled_user_id = await seed_inactive_user(
        database_url, unique_email("disabled-seller"), "password123"
    )

    result = await create_order_by_seller(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        buyer_user_id=disabled_user_id,
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_self_purchase_returns_403(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """卖家指定本人为买家返回 403。"""
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None
    shop = shop_owner.root.step(ShopResult)
    assert shop.status_code == 201
    assert shop.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-self",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order_by_seller(
        client,
        headers=bearer_headers(owner),
        buyer_user_id=str(owner.body.user.id),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 403
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_cross_shop_product_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """提交的商品不属于本店返回 422，即使所有商品同属另一单一店铺。"""
    assert shop_owner.root.step(ShopResult).status_code == 201

    # 为 shop_owner 店铺准备一个可购商品
    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-own",
    )
    own_product = arranged.step(ProductResult)
    assert own_product.status_code == 201
    assert own_product.body is not None

    # 另开一家店及其商品
    other_shop = await register_and_open_shop(client)
    assert other_shop.step(ShopResult).status_code == 201
    other_category = await create_category(
        client,
        headers=bearer_headers(admin_auth_headers.root.step(LoginResult)),
        name=unique_category_name("cross-shop"),
    )
    assert other_category.status_code == 201
    assert other_category.body is not None
    other_product = await create_product(
        client,
        shop_owner=other_shop,
        category=other_category,
        is_published=True,
        name="other-shop-product",
    )
    assert other_product.status_code == 201
    assert other_product.body is not None

    result = await create_order_by_seller(
        client,
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
        buyer_user_id=str(uuid.uuid4()),
        items=[(other_product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_closed_shop_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店铺 closed 时建单返回 422。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-closed",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    # 关闭店铺
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    patch: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch.status_code == 200

    result = await create_order_by_seller(
        client,
        headers=owner_headers,
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证请求返回 401。"""
    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
        name="seller-order-unauth",
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await client.post(
        "/shops/me/orders",
        json={
            "buyer_user_id": str(uuid.uuid4()),
            "items": [{"product_id": product.body.id, "qty": 1}],
        },
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_no_shop_returns_404(
    client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """已认证但尚未开店的用户请求卖家建单返回 404。"""
    user = authenticated_user.root.step(RegisterResult)
    assert user.status_code == 201
    assert user.body is not None

    response: Response = await client.post(
        "/shops/me/orders",
        json={
            "buyer_user_id": str(uuid.uuid4()),
            "items": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
        headers=bearer_headers(user),
    )

    assert response.status_code == 404
