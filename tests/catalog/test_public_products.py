"""catalog 域 GET /products 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest

from tests.catalog.test_create_product import (
    _PRODUCT_FIELDS,
    _create_category_for_product,
)
from tests.conftest import create_category, register_and_open_shop, unique_category_name

_PAGINATED_FIELDS = {"items", "total", "limit", "offset"}


async def _create_product(
    client,
    admin_auth_headers,
    shop_owner,
    product_payload,
    *,
    is_published: bool = False,
    category_id: str | None = None,
) -> dict:
    """店主创建商品并返回响应体。"""
    if category_id is None:
        category_id = await _create_category_for_product(client, admin_auth_headers)
    payload = product_payload(
        category_ids=[category_id],
        primary_category_id=category_id,
        is_published=is_published,
    )
    response = await client.post(
        "/products",
        json=payload,
        headers=shop_owner["headers"],
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_products_returns_only_published_active(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """GET /products 仅返回已上架且店铺 active 的商品。"""
    assert shop_owner["status_code"] == 201

    published = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
    )
    await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=False,
    )

    response = await client.get("/products")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _PAGINATED_FIELDS
    assert isinstance(body["items"], list)

    returned_ids = {item["id"] for item in body["items"]}
    assert published["id"] in returned_ids
    for item in body["items"]:
        assert set(item.keys()) >= _PRODUCT_FIELDS
        assert item["is_published"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_products_filters_by_category_id(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """GET /products?category_id= 仅返回关联该类目的已上架商品。"""
    assert admin_auth_headers["status_code"] == 200
    assert shop_owner["status_code"] == 201

    cat_a = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=unique_category_name("filter-a"),
    )
    assert cat_a["status_code"] == 201
    cat_a_id = cat_a["json"]["id"]

    cat_b = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=unique_category_name("filter-b"),
    )
    assert cat_b["status_code"] == 201
    cat_b_id = cat_b["json"]["id"]

    in_a = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
        category_id=cat_a_id,
    )
    await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
        category_id=cat_b_id,
    )

    response = await client.get("/products", params={"category_id": cat_a_id})

    assert response.status_code == 200
    body = response.json()
    returned_ids = {item["id"] for item in body["items"]}
    assert in_a["id"] in returned_ids
    for item in body["items"]:
        category_ids = {c["id"] for c in item["categories"]}
        assert cat_a_id in category_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_200_when_published(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """已上架且店铺 active 时 GET /products/{id} 返回 200。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
    )

    response = await client.get(f"/products/{product['id']}")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _PRODUCT_FIELDS
    assert body["id"] == product["id"]
    assert body["is_published"] is True
    uuid.UUID(body["id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_404_when_unpublished(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """未上架商品 GET /products/{id} 返回 404。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=False,
    )

    response = await client.get(f"/products/{product['id']}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_product_detail_returns_404_when_shop_closed(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """所属店铺 closed 时 GET /products/{id} 返回 404。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
    )

    patch_response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner["headers"],
    )
    assert patch_response.status_code == 200

    response = await client.get(f"/products/{product['id']}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body
