"""catalog 域 PATCH /products/{id} integration 测试（TDD 红阶段）。"""

import pytest
from httpx import Response

from app.catalog.schemas import ProductResponse
from tests.catalog.test_create_product import _create_product
from tests.conftest import register_and_open_shop
from tests.support.contexts import ShopOwnerContext


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_success_returns_200(
    client, admin_auth_headers, shop_owner
) -> None:
    """店主 PATCH 本店商品合法字段成功，返回 200 与 ProductResponse。"""
    assert shop_owner.status_code == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        is_published=False,
    )

    response: Response = await client.patch(
        f"/products/{product.id}",
        json={"is_published": True, "description": "更新后的简介"},
        headers=shop_owner.headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.id == product.id
    assert body.is_published is True
    assert body.description == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_other_shop_returns_403(
    client, admin_auth_headers
) -> None:
    """店主 PATCH 其他店铺商品返回 403。"""
    owner_a: ShopOwnerContext = await register_and_open_shop(client)
    assert owner_a.status_code == 201

    owner_b: ShopOwnerContext = await register_and_open_shop(client)
    assert owner_b.status_code == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        owner_a,
    )

    response: Response = await client.patch(
        f"/products/{product.id}",
        json={"name": "越权修改"},
        headers=owner_b.headers,
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_closed_shop_returns_422(
    client, admin_auth_headers, shop_owner
) -> None:
    """店铺 closed 时 PATCH 本店商品返回 422。"""
    assert shop_owner.status_code == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
    )

    patch_shop: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner.headers,
    )
    assert patch_shop.status_code == 200

    response: Response = await client.patch(
        f"/products/{product.id}",
        json={"name": "closed 店修改"},
        headers=shop_owner.headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_stock_zero_returns_200(
    client, admin_auth_headers, shop_owner
) -> None:
    """店主 PATCH 本店商品 stock 为 0 成功返回 200。"""
    assert shop_owner.status_code == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
    )
    assert product.stock > 0

    response: Response = await client.patch(
        f"/products/{product.id}",
        json={"stock": 0},
        headers=shop_owner.headers,
    )

    assert response.status_code == 200
    body = ProductResponse.model_validate(response.json())
    assert body.stock == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_product_delist_sets_is_published_false(
    client, admin_auth_headers, shop_owner
) -> None:
    """店主通过 PATCH is_published=false 下架商品，公开 GET 返回 404。"""
    assert shop_owner.status_code == 201

    product = await _create_product(
        client,
        admin_auth_headers,
        shop_owner,
        is_published=True,
    )

    patch_response: Response = await client.patch(
        f"/products/{product.id}",
        json={"is_published": False},
        headers=shop_owner.headers,
    )
    assert patch_response.status_code == 200
    assert ProductResponse.model_validate(patch_response.json()).is_published is False

    public_response: Response = await client.get(f"/products/{product.id}")
    assert public_response.status_code == 404
