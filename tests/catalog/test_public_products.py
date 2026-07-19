"""catalog 域 GET /products 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import Response

from app.catalog.schemas import PaginatedProducts, ProductResponse
from tests.support.builders import unique_category_name
from tests.support.contexts import AdminAuthContext, ShopOwnerContext
from tests.support.helpers import create_category, create_product
from tests.support.projections import bearer_headers
from tests.support.results import CategoryResult, LoginResult, ProductResult, RegisterResult, ShopResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_products_returns_only_published_active(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /products 仅返回已上架且店铺 active 的商品。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    admin_login = admin_auth_headers.root.step(LoginResult)
    assert admin_login.status_code == 200

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    published: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
        is_published=True,
    )
    assert published.status_code == 201
    assert published.body is not None

    unpublished: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=category,
        is_published=False,
    )
    assert unpublished.status_code == 201

    response: Response = await client.get("/products")

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())

    returned_ids = {item.id for item in body.items}
    assert published.body.id in returned_ids
    for item in body.items:
        assert item.is_published is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_products_filters_by_category_id(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /products?category_id= 仅返回关联该类目的已上架商品。"""
    admin_headers = bearer_headers(admin_auth_headers.root.step(LoginResult))
    assert admin_auth_headers.root.step(LoginResult).status_code == 200
    assert shop_owner.root.step(ShopResult).status_code == 201

    cat_a: CategoryResult = await create_category(
        client,
        headers=admin_headers,
        name=unique_category_name("filter-a"),
    )
    assert cat_a.status_code == 201
    assert cat_a.body is not None
    cat_a_id = cat_a.body.id

    cat_b: CategoryResult = await create_category(
        client,
        headers=admin_headers,
        name=unique_category_name("filter-b"),
    )
    assert cat_b.status_code == 201
    assert cat_b.body is not None

    in_a: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=cat_a,
        is_published=True,
    )
    assert in_a.status_code == 201
    assert in_a.body is not None

    in_b: ProductResult = await create_product(
        client,
        shop_owner=shop_owner.root,
        category=cat_b,
        is_published=True,
    )
    assert in_b.status_code == 201

    response: Response = await client.get("/products", params={"category_id": cat_a_id})

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())
    returned_ids = {item.id for item in body.items}
    assert in_a.body.id in returned_ids
    for item in body.items:
        category_ids = {c.id for c in item.categories}
        assert cat_a_id in category_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_200_when_published(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """已上架且店铺 active 时 GET /products/{id} 返回 200。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
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

    response: Response = await client.get(f"/products/{product.body.id}")

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.id == product.body.id
    assert body.is_published is True
    uuid.UUID(body.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_404_when_unpublished(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """未上架商品 GET /products/{id} 返回 404。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
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

    response: Response = await client.get(f"/products/{product.body.id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_404_when_shop_closed(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """所属店铺 closed 时 GET /products/{id} 返回 404。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
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
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
    )
    assert patch_response.status_code == 200

    response: Response = await client.get(f"/products/{product.body.id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body
