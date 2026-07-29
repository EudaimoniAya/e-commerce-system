"""catalog 域 PATCH /products/{id} integration 测试（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import ProductResponse
from tests.support.builders import unique_category_name
from tests.support.contexts import ShopOwnerContext
from tests.support.helper.catalog import register_and_open_shop
from tests.support.db.catalog import seed_category, seed_product, seed_product_category
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("update_product")
@allure.title("店主 PATCH 本店商品合法字段成功，返回 200 与 ProductResponse")
async def test_patch_product_success_returns_200(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 PATCH 本店商品合法字段成功，返回 200 与 ProductResponse。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    product_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("product"),
        is_published=False,
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )

    response: Response = await integration_client.patch(
        f"/products/{product_id}",
        json={"is_published": True, "description": "更新后的简介"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.id == product_id
    assert body.is_published is True
    assert body.description == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("update_product")
@allure.title("店主 PATCH 其他店铺商品返回 403")
async def test_patch_product_other_shop_returns_403(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """店主 PATCH 其他店铺商品返回 403。"""
    owner_a_reg, owner_a_shop = await register_and_open_shop(integration_client)
    assert owner_a_shop is not None and owner_a_shop.status_code == 201

    owner_b_reg, owner_b_shop = await register_and_open_shop(integration_client)
    assert owner_b_shop is not None and owner_b_shop.status_code == 201

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    product_id = await seed_product(
        db_session,
        shop_id=owner_a_shop.body.id,
        name=unique_category_name("product"),
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )

    response: Response = await integration_client.patch(
        f"/products/{product_id}",
        json={"name": "越权修改"},
        headers=bearer_headers(owner_b_reg.body.access_token),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("update_product")
@allure.title("店铺 closed 时 PATCH 本店商品返回 422")
async def test_patch_product_closed_shop_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店铺 closed 时 PATCH 本店商品返回 422。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    product_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("product"),
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )

    patch_shop: Response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch_shop.status_code == 200

    response: Response = await integration_client.patch(
        f"/products/{product_id}",
        json={"name": "closed 店修改"},
        headers=owner_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "error" in body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("update_product")
@allure.title("店主 PATCH 本店商品 stock 为 0 成功返回 200")
async def test_patch_product_stock_zero_returns_200(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 PATCH 本店商品 stock 为 0 成功返回 200。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    product_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("product"),
        stock=10,
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )

    response: Response = await integration_client.patch(
        f"/products/{product_id}",
        json={"stock": 0},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.stock == 0


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("update_product")
@allure.title("店主通过 PATCH is_published=false 下架商品，公开 GET 返回 404")
async def test_patch_product_delist_sets_is_published_false(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主通过 PATCH is_published=false 下架商品，公开 GET 返回 404。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    product_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("product"),
        is_published=True,
    )
    await seed_product_category(
        db_session,
        product_id=product_id,
        category_id=category_id,
        is_primary=True,
    )

    patch_response: Response = await integration_client.patch(
        f"/products/{product_id}",
        json={"is_published": False},
        headers=owner_headers,
    )
    assert patch_response.status_code == 200
    assert ProductResponse.model_validate(patch_response.json()).is_published is False

    public_response: Response = await integration_client.get(
        f"/products/{product_id}"
    )
    assert public_response.status_code == 404
