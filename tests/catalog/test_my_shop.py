"""catalog 域 GET/PATCH /shops/me integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ShopResponse
from tests.support.helpers import register_and_open_shop
from tests.support.builders import unique_shop_name
from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import RegisterResult, ShopResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_returns_200_when_owner_has_shop(
    client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """已认证店主查询 /shops/me 返回 200 与完整店铺对象。"""
    shop_result = shop_owner.root.step(ShopResult)
    registered = shop_owner.root.step(RegisterResult)
    assert shop_result.status_code == 201
    assert shop_result.body is not None
    assert registered.body is not None
    assert registered.body.user is not None

    response: Response = await client.get(
        "/shops/me", headers=bearer_headers(registered)
    )

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.id == shop_result.body.id
    assert body.owner_user_id == registered.body.user.id
    assert body.name == shop_result.request.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_returns_404_when_no_shop(
    client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证但尚无店铺的用户查询 /shops/me 返回 404。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201

    response: Response = await client.get(
        "/shops/me", headers=bearer_headers(registered)
    )

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_my_shop_unauthenticated_returns_401(client: AsyncClient) -> None:
    """未携带 Bearer token 查询 /shops/me 返回 401。"""
    response: Response = await client.get("/shops/me")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_returns_200(client: AsyncClient, shop_owner: ShopOwnerContext) -> None:
    """店主 PATCH /shops/me 更新字段成功返回 200。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    new_name = unique_shop_name("updated")

    response: Response = await client.patch(
        "/shops/me",
        json={"name": new_name, "description": "更新后的简介"},
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
    )

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.name == new_name
    assert body.description == "更新后的简介"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_status_closed_returns_200(
    client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """店主 PATCH /shops/me 设置 status 为 closed 返回 200。"""
    assert shop_owner.root.step(ShopResult).status_code == 201

    response: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
    )

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.status == "closed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_returns_404_when_no_shop(
    client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证但尚无店铺的用户 PATCH /shops/me 返回 404。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201

    response: Response = await client.patch(
        "/shops/me",
        json={"name": unique_shop_name("no-shop")},
        headers=bearer_headers(registered),
    )

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_name_conflict_returns_422(client: AsyncClient) -> None:
    """店主 PATCH 店名与其他店铺冲突时返回 422。"""
    taken_name = unique_shop_name("taken")
    first: PipelineResult = await register_and_open_shop(client, shop_name=taken_name)
    assert first.step(ShopResult).status_code == 201

    second: PipelineResult = await register_and_open_shop(client)
    assert second.step(ShopResult).status_code == 201

    response: Response = await client.patch(
        "/shops/me",
        json={"name": taken_name},
        headers=bearer_headers(second.step(RegisterResult)),
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_my_shop_unauthenticated_returns_401(client: AsyncClient) -> None:
    """未携带 Bearer token PATCH /shops/me 返回 401。"""
    response: Response = await client.patch(
        "/shops/me",
        json={"name": unique_shop_name("anon")},
    )

    assert response.status_code == 401
