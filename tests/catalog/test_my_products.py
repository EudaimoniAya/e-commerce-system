"""catalog 域 GET /shops/me/products integration 测试（TDD 红阶段）。"""

import pytest

from tests.catalog.test_create_product import (
    _CATEGORY_ITEM_FIELDS,
    _PRODUCT_FIELDS,
    _create_category_for_product,
)
from tests.conftest import register_and_open_shop

_PAGINATED_FIELDS = {"items", "total", "limit", "offset"}


async def _create_product(
    client,
    admin_auth_headers,
    shop_owner,
    product_payload,
    *,
    is_published: bool = False,
) -> dict:
    """店主创建商品并返回响应体。"""
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
async def test_get_my_products_returns_200_with_all_products(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店主 GET /shops/me/products 返回 200，含未上架商品。"""
    assert shop_owner["status_code"] == 201

    published = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
    )
    unpublished = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=False,
    )

    response = await client.get(
        "/shops/me/products",
        headers=shop_owner["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _PAGINATED_FIELDS
    assert isinstance(body["items"], list)
    assert body["total"] >= 2

    by_id = {item["id"]: item for item in body["items"]}
    assert published["id"] in by_id
    assert unpublished["id"] in by_id
    for product_id in (published["id"], unpublished["id"]):
        item = by_id[product_id]
        assert set(item.keys()) >= _PRODUCT_FIELDS
        assert isinstance(item["categories"], list)
        assert len(item["categories"]) >= 1
        assert set(item["categories"][0].keys()) >= _CATEGORY_ITEM_FIELDS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_returns_404_when_no_shop(
    client, authenticated_user
) -> None:
    """已认证但无店铺的用户 GET /shops/me/products 返回 404。"""
    assert authenticated_user["status_code"] == 201

    response = await client.get(
        "/shops/me/products",
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 404
    body = response.json()
    assert body == {"detail": "Shop not found"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_products_supports_pagination(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """GET /shops/me/products 支持 limit 与 offset 分页。"""
    assert shop_owner["status_code"] == 201

    created_ids: list[str] = []
    for _ in range(3):
        product = await _create_product(
            client,
            admin_auth_headers,
            shop_owner,
            product_payload,
        )
        created_ids.append(product["id"])

    first_page = await client.get(
        "/shops/me/products",
        params={"limit": 2, "offset": 0},
        headers=shop_owner["headers"],
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert set(first_body.keys()) >= _PAGINATED_FIELDS
    assert first_body["limit"] == 2
    assert first_body["offset"] == 0
    assert len(first_body["items"]) == 2
    assert first_body["total"] >= 3

    second_page = await client.get(
        "/shops/me/products",
        params={"limit": 2, "offset": 2},
        headers=shop_owner["headers"],
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert second_body["limit"] == 2
    assert second_body["offset"] == 2
    assert len(second_body["items"]) >= 1

    first_ids = {item["id"] for item in first_body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids <= set(created_ids)
