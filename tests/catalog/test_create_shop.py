"""catalog 域 POST /shops integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ShopResponse
from tests.support.helper.auth import auth_headers, register_user
from tests.support.helper.catalog import register_and_open_shop
from tests.support.builders import build_shop_create, unique_shop_name
from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.utils import bearer_headers
from tests.support.results import RegisterResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_success_returns_201(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证用户提交有效店名开店成功，返回 201 与完整店铺资料。"""
    shop_request = build_shop_create(
        description="测试店铺简介",
        logo_url="https://example.com/logo.png",
    )
    response: Response = await integration_client.post(
        "/shops",
        json=shop_request.model_dump(mode="json"),
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 201
    body = ShopResponse.model_validate(response.json())
    assert body.name == shop_request.name
    assert body.description == shop_request.description
    assert body.logo_url == shop_request.logo_url
    assert body.status == "active"
    uuid.UUID(body.owner_user_id)
    uuid.UUID(body.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_duplicate_returns_422(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """同一用户重复开店返回 422。"""
    response: Response = await integration_client.post(
        "/shops",
        json=build_shop_create().model_dump(mode="json"),
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "error" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_name_conflict_returns_422(
    integration_client: AsyncClient,
) -> None:
    """店名已被其他店铺使用时返回 422。"""
    shop_name = unique_shop_name("conflict")
    first_reg, first_shop = await register_and_open_shop(
        integration_client, shop_name=shop_name
    )
    assert first_shop is not None
    assert first_shop.status_code == 201

    second_user: RegisterResult = await register_user(integration_client)
    assert second_user.status_code == 201
    assert second_user.body is not None

    response: Response = await integration_client.post(
        "/shops",
        json=build_shop_create(name=shop_name).model_dump(mode="json"),
        headers=auth_headers(second_user.body.access_token),
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "error" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shop_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未携带 Bearer token 开店返回 401。"""
    response: Response = await integration_client.post(
        "/shops",
        json=build_shop_create().model_dump(mode="json"),
    )

    assert response.status_code == 401
