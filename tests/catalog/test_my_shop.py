"""catalog 域 GET/PATCH /shops/me integration 测试（TDD 红阶段）。"""

import pytest

from tests.conftest import (
    register_and_open_shop,
    unique_shop_name,
)

from tests.catalog.test_create_shop import _SHOP_FIELDS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_returns_200_when_owner_has_shop(client, shop_owner) -> None:
    """已认证店主查询 /shops/me 返回 200 与完整店铺对象。"""
    assert shop_owner["status_code"] == 201

    response = await client.get("/shops/me", headers=shop_owner["headers"])

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _SHOP_FIELDS
    assert body["id"] == shop_owner["json"]["id"]
    assert body["owner_user_id"] == shop_owner["user"]["id"]
    assert body["name"] == shop_owner["shop_payload"]["name"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_returns_404_when_no_shop(client, authenticated_user) -> None:
    """已认证但尚无店铺的用户查询 /shops/me 返回 404。"""
    assert authenticated_user["status_code"] == 201

    response = await client.get("/shops/me", headers=authenticated_user["headers"])

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_unauthenticated_returns_401(client) -> None:
    """未携带 Bearer token 查询 /shops/me 返回 401。"""
    response = await client.get("/shops/me")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_returns_200(client, shop_owner) -> None:
    """店主 PATCH /shops/me 更新字段成功返回 200。"""
    assert shop_owner["status_code"] == 201
    new_name = unique_shop_name("updated")

    response = await client.patch(
        "/shops/me",
        json={"name": new_name, "description": "更新后的简介"},
        headers=shop_owner["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _SHOP_FIELDS
    assert body["name"] == new_name
    assert body["description"] == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_status_closed_returns_200(client, shop_owner) -> None:
    """店主 PATCH /shops/me 设置 status 为 closed 返回 200。"""
    assert shop_owner["status_code"] == 201

    response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_returns_404_when_no_shop(
    client, authenticated_user
) -> None:
    """已认证但尚无店铺的用户 PATCH /shops/me 返回 404。"""
    assert authenticated_user["status_code"] == 201

    response = await client.patch(
        "/shops/me",
        json={"name": unique_shop_name("no-shop")},
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_name_conflict_returns_422(client) -> None:
    """店主 PATCH 店名与其他店铺冲突时返回 422。"""
    taken_name = unique_shop_name("taken")
    first = await register_and_open_shop(client, shop_name=taken_name)
    assert first["status_code"] == 201

    second = await register_and_open_shop(client)
    assert second["status_code"] == 201

    response = await client.patch(
        "/shops/me",
        json={"name": taken_name},
        headers=second["headers"],
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_unauthenticated_returns_401(client) -> None:
    """未携带 Bearer token PATCH /shops/me 返回 401。"""
    response = await client.patch(
        "/shops/me",
        json={"name": unique_shop_name("anon")},
    )

    assert response.status_code == 401
