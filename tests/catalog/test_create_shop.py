"""catalog 域 POST /shops integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import Response

from app.catalog.schemas import ShopResponse
from tests.support.helpers import (
    auth_headers,
    register_and_open_shop,
    register_user,
)
from tests.support.builders import build_shop_create, unique_shop_name
from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import RegisterResult, ShopResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_success_returns_201(
    client, authenticated_user: AuthContext
) -> None:
    """已认证用户提交有效店名开店成功，返回 201 与完整店铺资料。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201
    assert registered.body is not None
    assert registered.body.user is not None

    shop_request = build_shop_create(
        description="测试店铺简介",
        logo_url="https://example.com/logo.png",
    )
    response: Response = await client.post(
        "/shops",
        json=shop_request.model_dump(mode="json"),
        headers=bearer_headers(registered),
    )

    assert response.status_code == 201
    body = ShopResponse.model_validate(response.json())
    assert body.name == shop_request.name
    assert body.description == shop_request.description
    assert body.logo_url == shop_request.logo_url
    assert body.status == "active"
    assert body.owner_user_id == registered.body.user.id
    uuid.UUID(body.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_duplicate_returns_422(
    client, shop_owner: ShopOwnerContext
) -> None:
    """同一用户重复开店返回 422。"""
    assert shop_owner.root.step(ShopResult).status_code == 201

    response: Response = await client.post(
        "/shops",
        json=build_shop_create().model_dump(mode="json"),
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
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
    first: PipelineResult = await register_and_open_shop(client, shop_name=shop_name)
    assert first.step(ShopResult).status_code == 201

    second_user: RegisterResult = await register_user(client)
    assert second_user.status_code == 201
    assert second_user.body is not None

    response: Response = await client.post(
        "/shops",
        json=build_shop_create(name=shop_name).model_dump(mode="json"),
        headers=auth_headers(second_user.body.access_token),
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_unauthenticated_returns_401(client) -> None:
    """未携带 Bearer token 开店返回 401。"""
    response: Response = await client.post(
        "/shops",
        json=build_shop_create().model_dump(mode="json"),
    )

    assert response.status_code == 401
