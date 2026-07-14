"""catalog 域 POST /shops integration 测试（TDD 红阶段）。"""

import uuid

import pytest

from tests.conftest import (
    auth_headers,
    create_shop_payload,
    register_and_open_shop,
    register_user,
    unique_shop_name,
)

_SHOP_FIELDS = {
    "id",
    "owner_user_id",
    "name",
    "description",
    "logo_url",
    "status",
    "created_at",
    "updated_at",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_success_returns_201(client, authenticated_user) -> None:
    """已认证用户提交有效店名开店成功，返回 201 与完整店铺资料。"""
    assert authenticated_user["status_code"] == 201

    payload = create_shop_payload(
        description="测试店铺简介",
        logo_url="https://example.com/logo.png",
    )
    response = await client.post(
        "/shops",
        json=payload,
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) >= _SHOP_FIELDS
    assert body["name"] == payload["name"]
    assert body["description"] == payload["description"]
    assert body["logo_url"] == payload["logo_url"]
    assert body["status"] == "active"
    assert body["owner_user_id"] == authenticated_user["user"]["id"]
    uuid.UUID(body["id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_duplicate_returns_422(client, shop_owner) -> None:
    """同一用户重复开店返回 422。"""
    assert shop_owner["status_code"] == 201

    response = await client.post(
        "/shops",
        json=create_shop_payload(),
        headers=shop_owner["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_name_conflict_returns_422(client) -> None:
    """店名已被其他店铺使用时返回 422。"""
    shop_name = unique_shop_name("conflict")
    first = await register_and_open_shop(client, shop_name=shop_name)
    assert first["status_code"] == 201

    second_user = await register_user(client)
    assert second_user["status_code"] == 201
    access_token = second_user["json"]["access_token"]

    response = await client.post(
        "/shops",
        json=create_shop_payload(name=shop_name),
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_unauthenticated_returns_401(client) -> None:
    """未携带 Bearer token 开店返回 401。"""
    response = await client.post("/shops", json=create_shop_payload())

    assert response.status_code == 401
