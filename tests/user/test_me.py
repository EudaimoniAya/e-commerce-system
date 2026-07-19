"""user 域 GET /users/me integration 测试（TDD 红阶段）。"""

import pytest
from httpx import Response

from app.user.schemas import UserResponse
from tests.support.helpers import auth_headers
from tests.support.contexts import AuthContext
from tests.support.projections import bearer_headers
from tests.support.results import RegisterResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_200_with_valid_token(
    client, authenticated_user: AuthContext
) -> None:
    """有效 Bearer token 返回当前用户资料。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201
    assert registered.body is not None
    assert registered.body.user is not None

    response: Response = await client.get(
        "/users/me", headers=bearer_headers(registered)
    )
    assert response.status_code == 200

    body = UserResponse.model_validate(response.json())
    assert body.email == registered.body.user.email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_without_token_returns_401(client) -> None:
    """未携带 Authorization 返回 401。"""
    response: Response = await client.get("/users/me")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client) -> None:
    """无效 Bearer token 返回 401。"""
    response: Response = await client.get(
        "/users/me", headers=auth_headers("not-a-valid-jwt")
    )

    assert response.status_code == 401
