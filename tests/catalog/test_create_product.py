"""catalog 域 POST /products integration 测试（TDD 红阶段）。"""

import uuid

import pytest

from tests.conftest import create_category, unique_category_name

_PRODUCT_FIELDS = {
    "id",
    "shop_id",
    "name",
    "description",
    "price",
    "stock",
    "is_published",
    "image_url",
    "categories",
    "created_at",
    "updated_at",
}

_CATEGORY_ITEM_FIELDS = {"id", "name", "is_primary"}


async def _create_category_for_product(client, admin_auth_headers) -> str:
    """管理员创建测试用类目，返回 category id。"""
    assert admin_auth_headers["status_code"] == 200
    result = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=unique_category_name("product"),
    )
    assert result["status_code"] == 201
    return result["json"]["id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_success_returns_201(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店主在 active 店铺下创建商品成功，返回 201 与 ProductResponse。"""
    assert shop_owner["status_code"] == 201

    category_id = await _create_category_for_product(client, admin_auth_headers)
    payload = product_payload(
        description="测试商品简介",
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response = await client.post(
        "/products",
        json=payload,
        headers=shop_owner["headers"],
    )

    assert response.status_code == 201
    body = response.json()
    assert body is not None
    assert set(body.keys()) >= _PRODUCT_FIELDS
    assert body["name"] == payload["name"]
    assert body["description"] == payload["description"]
    assert body["price"] == payload["price"]
    assert body["stock"] == payload["stock"]
    assert body["is_published"] is False
    assert body["shop_id"] == shop_owner["json"]["id"]
    uuid.UUID(body["id"])

    assert isinstance(body["categories"], list)
    assert len(body["categories"]) >= 1
    primary = next(c for c in body["categories"] if c["is_primary"])
    assert set(primary.keys()) >= _CATEGORY_ITEM_FIELDS
    assert primary["id"] == category_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_closed_shop_returns_422(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店铺 status 为 closed 时 POST /products 返回 422。"""
    assert shop_owner["status_code"] == 201

    patch_response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner["headers"],
    )
    assert patch_response.status_code == 200

    category_id = await _create_category_for_product(client, admin_auth_headers)
    payload = product_payload(
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response = await client.post(
        "/products",
        json=payload,
        headers=shop_owner["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_no_shop_returns_404(
    client, admin_auth_headers, authenticated_user, product_payload
) -> None:
    """已认证但无店铺的用户 POST /products 返回 404。"""
    assert authenticated_user["status_code"] == 201

    category_id = await _create_category_for_product(client, admin_auth_headers)
    payload = product_payload(
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response = await client.post(
        "/products",
        json=payload,
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_empty_category_ids_returns_422(
    client, shop_owner, product_payload
) -> None:
    """category_ids 为空时 POST /products 返回 422。"""
    assert shop_owner["status_code"] == 201

    payload = product_payload(
        category_ids=[],
        primary_category_id=str(uuid.uuid4()),
    )

    response = await client.post(
        "/products",
        json=payload,
        headers=shop_owner["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_invalid_primary_category_returns_422(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """primary_category_id 不在 category_ids 中时 POST /products 返回 422。"""
    assert shop_owner["status_code"] == 201

    category_id = await _create_category_for_product(client, admin_auth_headers)
    payload = product_payload(
        category_ids=[category_id],
        primary_category_id=str(uuid.uuid4()),
    )

    response = await client.post(
        "/products",
        json=payload,
        headers=shop_owner["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body
