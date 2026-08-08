"""user 域 GET /users/me integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md MODIFIED Requirement）：
- 有效 token 返回当前用户（含 phone、email 可 null）
- 无 token → 401
- token 无效 → 401
"""

import allure
import pytest
from httpx import AsyncClient

from app.user.schemas import UserResponse
from tests.testkit.contexts import AuthContext
from tests.testkit.helper.auth import auth_headers
from tests.testkit.utils import bearer_headers


@allure.epic("user")
@allure.feature("me")
@allure.title("有效 Bearer token 返回当前用户资料（含 phone）。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_200_with_valid_token(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """有效 Bearer token 返回当前用户资料（含 phone）。"""
    headers = bearer_headers(authenticated_user.access_token)

    response = await integration_client.get("/users/me", headers=headers)
    assert response.status_code == 200

    body = UserResponse.model_validate(response.json())
    assert body.phone == authenticated_user.phone


@allure.epic("user")
@allure.feature("me")
@allure.title("未携带 Authorization 返回 401。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_without_token_returns_401(integration_client: AsyncClient) -> None:
    """未携带 Authorization 返回 401。"""
    response = await integration_client.get("/users/me")
    assert response.status_code == 401


@allure.epic("user")
@allure.feature("me")
@allure.title("无效 Bearer token 返回 401。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(
    integration_client: AsyncClient,
) -> None:
    """无效 Bearer token 返回 401。"""
    response = await integration_client.get(
        "/users/me", headers=auth_headers("not-a-valid-jwt")
    )
    assert response.status_code == 401
