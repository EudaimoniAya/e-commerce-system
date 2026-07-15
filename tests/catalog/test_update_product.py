"""catalog 域 PATCH /products/{id} integration 测试（TDD 红阶段）。"""

import pytest

from tests.catalog.test_create_product import (
    _PRODUCT_FIELDS,
    _create_category_for_product,
)
from tests.conftest import register_and_open_shop


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
async def test_patch_product_success_returns_200(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店主 PATCH 本店商品合法字段成功，返回 200 与 ProductResponse。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=False,
    )

    response = await client.patch(
        f"/products/{product['id']}",
        json={"is_published": True, "description": "更新后的简介"},
        headers=shop_owner["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _PRODUCT_FIELDS
    assert body["id"] == product["id"]
    assert body["is_published"] is True
    assert body["description"] == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_other_shop_returns_403(
    client, admin_auth_headers, product_payload
) -> None:
    """店主 PATCH 其他店铺商品返回 403。"""
    owner_a = await register_and_open_shop(client)
    assert owner_a["status_code"] == 201

    owner_b = await register_and_open_shop(client)
    assert owner_b["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        owner_a,
        product_payload,
    )

    response = await client.patch(
        f"/products/{product['id']}",
        json={"name": "越权修改"},
        headers=owner_b["headers"],
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_closed_shop_returns_422(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店铺 closed 时 PATCH 本店商品返回 422。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
    )

    patch_shop = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner["headers"],
    )
    assert patch_shop.status_code == 200

    response = await client.patch(
        f"/products/{product['id']}",
        json={"name": "closed 店修改"},
        headers=shop_owner["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_stock_zero_returns_200(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店主 PATCH 本店商品 stock 为 0 成功返回 200。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
    )
    assert product["stock"] > 0

    response = await client.patch(
        f"/products/{product['id']}",
        json={"stock": 0},
        headers=shop_owner["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stock"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_delist_sets_is_published_false(
    client, admin_auth_headers, shop_owner, product_payload
) -> None:
    """店主通过 PATCH is_published=false 下架商品，公开 GET 返回 404。"""
    assert shop_owner["status_code"] == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        product_payload,
        is_published=True,
    )

    patch_response = await client.patch(
        f"/products/{product['id']}",
        json={"is_published": False},
        headers=shop_owner["headers"],
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["is_published"] is False

    public_response = await client.get(f"/products/{product['id']}")
    assert public_response.status_code == 404
