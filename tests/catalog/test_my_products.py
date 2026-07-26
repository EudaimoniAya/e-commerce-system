"""catalog 域 GET /shops/me/products integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import PaginatedProducts, ProductResponse
from tests.support.builders import unique_category_name
from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.catalog import seed_category, seed_product, seed_product_category
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_returns_200_with_all_products(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主 GET /shops/me/products 返回 200，含未上架商品。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    published_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("published"),
        is_published=True,
    )
    await seed_product_category(
        db_session,
        product_id=published_id,
        category_id=category_id,
        is_primary=True,
    )

    unpublished_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("unpublished"),
        is_published=False,
    )
    await seed_product_category(
        db_session,
        product_id=unpublished_id,
        category_id=category_id,
        is_primary=True,
    )

    response: Response = await integration_client.get(
        "/shops/me/products",
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())
    assert body.total >= 2

    by_id = {item.id: item for item in body.items}
    assert published_id in by_id
    assert unpublished_id in by_id
    for product_id in (published_id, unpublished_id):
        item = by_id[product_id]
        assert isinstance(item, ProductResponse)
        assert len(item.categories) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_returns_404_when_no_shop(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证但无店铺的用户 GET /shops/me/products 返回 404。"""
    response: Response = await integration_client.get(
        "/shops/me/products",
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Shop not found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_supports_pagination(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /shops/me/products 支持 limit 与 offset 分页。"""
    owner_headers = bearer_headers(shop_owner.access_token)

    category_id = await seed_category(
        db_session,
        name=unique_category_name("product"),
    )

    created_ids: list[str] = []
    for _ in range(3):
        product_id = await seed_product(
            db_session,
            shop_id=shop_owner.shop_id,
            name=unique_category_name("paginated"),
        )
        await seed_product_category(
            db_session,
            product_id=product_id,
            category_id=category_id,
            is_primary=True,
        )
        created_ids.append(product_id)

    first_page: Response = await integration_client.get(
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

    second_page: Response = await integration_client.get(
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
