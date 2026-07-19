"""catalog 域 GET /shops/me/products integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import PaginatedProducts, ProductResponse
from tests.support.builders import unique_category_name
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.helpers import create_category, create_product
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
async def test_get_my_products_returns_200_with_all_products(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 GET /shops/me/products 返回 200，含未上架商品。"""
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
    assert unpublished.body is not None

    response: Response = await client.get(
        "/shops/me/products",
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())
    assert body.total >= 2

    by_id = {item.id: item for item in body.items}
    assert published.body.id in by_id
    assert unpublished.body.id in by_id
    for product_id in (published.body.id, unpublished.body.id):
        item = by_id[product_id]
        assert isinstance(item, ProductResponse)
        assert len(item.categories) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_returns_404_when_no_shop(
    client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证但无店铺的用户 GET /shops/me/products 返回 404。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201

    response: Response = await client.get(
        "/shops/me/products",
        headers=bearer_headers(registered),
    )

    assert response.status_code == 404
    body = response.json()
    assert body == {"detail": "Shop not found"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_supports_pagination(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /shops/me/products 支持 limit 与 offset 分页。"""
    assert admin_auth_headers.root.step(LoginResult).status_code == 200
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))
    admin_login = admin_auth_headers.root.step(LoginResult)

    category: CategoryResult = await create_category(
        client,
        headers=bearer_headers(admin_login),
        name=unique_category_name("product"),
    )
    assert category.status_code == 201
    assert category.body is not None

    created_ids: list[str] = []
    for _ in range(3):
        product: ProductResult = await create_product(
            client,
            shop_owner=shop_owner.root,
            category=category,
        )
        assert product.status_code == 201
        assert product.body is not None
        created_ids.append(product.body.id)

    first_page: Response = await client.get(
        "/shops/me/products",
        params={"limit": 2, "offset": 0},
        headers=owner_headers,
    )
    assert first_page.status_code == 200
    first_body = PaginatedProducts.model_validate(first_page.json())
    assert first_body.limit == 2
    assert first_body.offset == 0
    assert len(first_body.items) == 2
    assert first_body.total >= 3

    second_page: Response = await client.get(
        "/shops/me/products",
        params={"limit": 2, "offset": 2},
        headers=owner_headers,
    )
    assert second_page.status_code == 200
    second_body = PaginatedProducts.model_validate(second_page.json())
    assert second_body.limit == 2
    assert second_body.offset == 2
    assert len(second_body.items) >= 1

    first_ids = {item.id for item in first_body.items}
    second_ids = {item.id for item in second_body.items}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids <= set(created_ids)
