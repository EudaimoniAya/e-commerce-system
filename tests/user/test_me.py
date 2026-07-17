"""user 域 GET /users/me integration 测试（TDD 红阶段）。"""

import pytest

from app.user.schemas import UserResponse
from tests.conftest import auth_headers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_200_with_valid_token(client, authenticated_user) -> None:
    """有效 Bearer token 返回当前用户资料。"""
    assert authenticated_user.status_code == 201
    assert authenticated_user.user is not None

    response = await client.get("/users/me", headers=authenticated_user.headers)
    assert response.status_code == 200

    body = UserResponse.model_validate(response.json())
    assert body.email == authenticated_user.user.email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_without_token_returns_401(client) -> None:
    """未携带 Authorization 返回 401。"""
    response = await client.get("/users/me")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client) -> None:
    """无效 Bearer token 返回 401。"""
    response = await client.get(
        "/users/me", headers=auth_headers("not-a-valid-jwt")
    )

    assert response.status_code == 401
