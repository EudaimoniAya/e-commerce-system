"""user 域 GET /users/me integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from app.user.schemas import UserResponse
from tests.support.helper.auth import auth_headers
from tests.support.contexts import AuthContext
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_200_with_valid_token(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """有效 Bearer token 返回当前用户资料。"""
    headers = bearer_headers(authenticated_user.access_token)

    response: Response = await integration_client.get(
        "/users/me", headers=headers
    )
    assert response.status_code == 200

    body = UserResponse.model_validate(response.json())
    assert body.email == authenticated_user.email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_without_token_returns_401(integration_client: AsyncClient) -> None:
    """未携带 Authorization 返回 401。"""
    response: Response = await integration_client.get("/users/me")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(integration_client: AsyncClient) -> None:
    """无效 Bearer token 返回 401。"""
    response: Response = await integration_client.get(
        "/users/me", headers=auth_headers("not-a-valid-jwt")
    )

    assert response.status_code == 401
