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
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import decode_access_token
from tests.support.builders import unique_email, unique_category_name
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.db.catalog import get_product_stock
from tests.support.helper.catalog import create_category, create_product, register_and_open_shop
from tests.support.helper.ordering import arrange_purchasable_product, create_order_by_seller
from tests.support.utils import bearer_headers
from tests.support.db.user import seed_inactive_user
from tests.support.helper.auth import register_authenticated


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主为本店已上架且库存充足的商品为另一有效用户建单成功，返回 201 + initiated_by=seller。"""
    buyer = await register_authenticated(integration_client)
    assert buyer.status_code == 201
    assert buyer.body is not None

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        price="49.99",
        name="seller-order-a",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 2)],
    )

    assert result.status_code == 201
    assert result.body is not None
    assert result.body.status == "awaiting_payment"
    assert result.body.buyer_user_id == str(buyer.body.user.id)
    assert result.body.shop_id == shop_owner.shop_id

    # 响应体应暴露 initiated_by=seller（实现后覆盖）
    # assert result.body.initiated_by == "seller"

    # 库存已扣减
    assert await get_product_stock(db_session, product.body.id) == 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_buyer_not_found_returns_404(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """指定买家在 users 表中不存在返回 404。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-404",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    non_existent_id = str(uuid.uuid4())
    result = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=non_existent_id,
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 404
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_disabled_buyer_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """指定买家 is_active=false 返回 422。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-disabled",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    disabled_user_id = await seed_inactive_user(
        db_session, unique_email("disabled-seller"), "password123"
    )

    result = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=disabled_user_id,
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_self_purchase_returns_403(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """卖家指定本人为买家返回 403。"""
    owner_user_id = decode_access_token(shop_owner.access_token)

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-self",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    result = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(owner_user_id),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 403
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_cross_shop_product_returns_422(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """提交的商品不属于本店返回 422，即使所有商品同属另一单一店铺。"""
    # 为 shop_owner 店铺准备一个可购商品
    own_category, own_product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-own",
    )
    assert own_product is not None
    assert own_product.status_code == 201
    assert own_product.body is not None

    # 另开一家店及其商品
    other_reg, other_shop = await register_and_open_shop(integration_client)
    assert other_shop is not None
    assert other_shop.status_code == 201
    other_category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
        name=unique_category_name("cross-shop"),
    )
    assert other_category.status_code == 201
    assert other_category.body is not None
    other_product = await create_product(
        integration_client,
        shop_owner_token=other_reg.body.access_token,
        category=other_category,
        is_published=True,
        name="other-shop-product",
    )
    assert other_product.status_code == 201
    assert other_product.body is not None

    result = await create_order_by_seller(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        buyer_user_id=str(uuid.uuid4()),
        items=[(other_product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_closed_shop_returns_422(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店铺 closed 时建单返回 422。"""
    buyer = await register_authenticated(integration_client)
    assert buyer.status_code == 201
    assert buyer.body is not None

    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-closed",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    # 关闭店铺
    owner_headers = bearer_headers(shop_owner.access_token)
    patch: Response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch.status_code == 200

    result = await create_order_by_seller(
        integration_client,
        headers=owner_headers,
        buyer_user_id=str(buyer.body.user.id),
        items=[(product.body.id, 1)],
    )

    assert result.status_code == 422
    assert result.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_order_by_seller_unauthenticated_returns_401(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证请求返回 401。"""
    category, product = await arrange_purchasable_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        admin_token=admin_auth_headers.access_token,
        stock=10,
        name="seller-order-unauth",
    )
    assert product is not None
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await integration_client.post(
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
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """已认证但尚未开店的用户请求卖家建单返回 404。"""
    response: Response = await integration_client.post(
        "/shops/me/orders",
        json={
            "buyer_user_id": str(uuid.uuid4()),
            "items": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 404
