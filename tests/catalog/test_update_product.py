"""catalog 域 PATCH /products/{id} integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ProductResponse
from tests.support.builders import unique_category_name
from tests.support.contexts import AdminAuthContext, ShopOwnerContext
from tests.support.helpers import create_category, create_product, register_and_open_shop
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import (
    CategoryResult,
    LoginResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_success_returns_200(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 PATCH 本店商品合法字段成功，返回 200 与 ProductResponse。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    product: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
        is_published=False,
    )
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await client.patch(
        f"/products/{product.body.id}",
        json={"is_published": True, "description": "更新后的简介"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.id == product.body.id
    assert body.is_published is True
    assert body.description == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_other_shop_returns_403(
    client: AsyncClient, admin_auth_headers: AdminAuthContext
) -> None:
    """店主 PATCH 其他店铺商品返回 403。"""
    owner_a: PipelineResult = await register_and_open_shop(client)
    assert owner_a.step(ShopResult).status_code == 201

    owner_b: PipelineResult = await register_and_open_shop(client)
    assert owner_b.step(ShopResult).status_code == 201

    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200
    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    product: ProductResult = await create_product(
        client,
        shop_owner=owner_a,
        category=category,
    )
    assert product.status_code == 201
    assert product.body is not None

    response: Response = await client.patch(
        f"/products/{product.body.id}",
        json={"name": "越权修改"},
        headers=bearer_headers(owner_b.step(RegisterResult)),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_closed_shop_returns_422(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店铺 closed 时 PATCH 本店商品返回 422。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    product: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
    )
    assert product.status_code == 201
    assert product.body is not None

    patch_shop: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch_shop.status_code == 200

    response: Response = await client.patch(
        f"/products/{product.body.id}",
        json={"name": "closed 店修改"},
        headers=owner_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_stock_zero_returns_200(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 PATCH 本店商品 stock 为 0 成功返回 200。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    product: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
    )
    assert product.status_code == 201
    assert product.body is not None
    assert product.body.stock > 0

    response: Response = await client.patch(
        f"/products/{product.body.id}",
        json={"stock": 0},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.stock == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_delist_sets_is_published_false(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主通过 PATCH is_published=false 下架商品，公开 GET 返回 404。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    product: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
        is_published=True,
    )
    assert product.status_code == 201
    assert product.body is not None

    patch_response: Response = await client.patch(
        f"/products/{product.body.id}",
        json={"is_published": False},
        headers=owner_headers,
    )
    assert patch_response.status_code == 200
    assert ProductResponse.model_validate(patch_response.json()).is_published is False

    public_response: Response = await client.get(f"/products/{product.body.id}")
    assert public_response.status_code == 404
