"""user 域 PATCH /users/me integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md ADDED Requirement）：
- 更新 email 与 nickname 成功返回 200
- 未认证请求返回 401

.. note::
    email 冲突 422 场景需依赖其他用户具有目标 email，在 service 层测试更合适。
"""

import allure
import pytest
from httpx import AsyncClient

from app.user.schemas import UserProfileUpdateRequest
from tests.support.contexts import AuthContext
from tests.support.utils import bearer_headers


@allure.epic("user")
@allure.feature("profile")
@allure.title("更新 email 与 nickname 返回 200。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_profile_success_returns_200(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """更新 email 与 nickname 返回 200。"""
    headers = bearer_headers(authenticated_user.access_token)
    body = UserProfileUpdateRequest(
        email="newemail@example.com", nickname="新昵称"
    )
    response = await integration_client.patch(
        "/users/me",
        json=body.model_dump(exclude_none=True),
        headers=headers,
    )
    assert response.status_code == 200

    updated = response.json()
    assert updated["email"] == "newemail@example.com"
    assert updated["nickname"] == "新昵称"


@allure.epic("user")
@allure.feature("profile")
@allure.title("未认证请求 PATCH /users/me 返回 401。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_patch_profile_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证请求 PATCH /users/me 返回 401。"""
    body = UserProfileUpdateRequest(nickname="test")
    response = await integration_client.patch(
        "/users/me",
        json=body.model_dump(exclude_none=True),
    )
    assert response.status_code == 401
