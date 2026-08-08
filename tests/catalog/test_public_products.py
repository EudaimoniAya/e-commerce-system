"""catalog 域 GET /products 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import allure
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import PaginatedProducts, ProductResponse
from tests.testkit.builders import unique_category_name
from tests.testkit.contexts import ShopOwnerContext
from tests.testkit.db.catalog import seed_category, seed_product, seed_product_category
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_products")
@allure.title("GET /products 仅返回已上架且店铺 active 的商品")
async def test_get_public_products_returns_only_published_active(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /products 仅返回已上架且店铺 active 的商品。"""
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

    response: Response = await integration_client.get("/products")

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())

    returned_ids = {item.id for item in body.items}
    assert published_id in returned_ids
    for item in body.items:
        assert item.is_published is True


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_products")
@allure.title("GET /products?category_id= 仅返回关联该类目的已上架商品")
async def test_get_public_products_filters_by_category_id(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """GET /products?category_id= 仅返回关联该类目的已上架商品。"""
    cat_a_id = await seed_category(
        db_session,
        name=unique_category_name("filter-a"),
    )

    cat_b_id = await seed_category(
        db_session,
        name=unique_category_name("filter-b"),
    )

    in_a_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("in-a"),
        is_published=True,
    )
    await seed_product_category(
        db_session,
        product_id=in_a_id,
        category_id=cat_a_id,
        is_primary=True,
    )

    in_b_id = await seed_product(
        db_session,
        shop_id=shop_owner.shop_id,
        name=unique_category_name("in-b"),
        is_published=True,
    )
    await seed_product_category(
        db_session,
        product_id=in_b_id,
        category_id=cat_b_id,
        is_primary=True,
    )

    response: Response = await integration_client.get(
        "/products", params={"category_id": cat_a_id}
    )

    assert response.status_code == 200
    body = PaginatedProducts.model_validate(response.json())
    returned_ids = {item.id for item in body.items}
    assert in_a_id in returned_ids
    for item in body.items:
        category_ids = {c.id for c in item.categories}
        assert cat_a_id in category_ids


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_products")
@allure.title("已上架且店铺 active 时 GET /products/{id} 返回 200")
async def test_get_public_product_detail_returns_200_when_published(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """已上架且店铺 active 时 GET /products/{id} 返回 200。"""
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

    response: Response = await integration_client.get(f"/products/{product_id}")

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.id == product_id
    assert body.is_published is True
    uuid.UUID(body.id)


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_products")
@allure.title("未上架商品 GET /products/{id} 返回 404")
async def test_get_public_product_detail_returns_404_when_unpublished(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """未上架商品 GET /products/{id} 返回 404。"""
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

    response: Response = await integration_client.get(f"/products/{product_id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "error" in body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_products")
@allure.title("所属店铺 closed 时 GET /products/{id} 返回 404")
async def test_get_public_product_detail_returns_404_when_shop_closed(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """所属店铺 closed 时 GET /products/{id} 返回 404。"""
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
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(shop_owner.access_token),
    )
    assert patch_response.status_code == 200

    response: Response = await integration_client.get(f"/products/{product_id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "error" in body
