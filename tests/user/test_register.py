"""user 域注册端点 integration 测试（TDD 红阶段）。"""

import re
import uuid

import pytest
from httpx import AsyncClient, Response

from tests.support.helper.auth import register_user
from tests.support.builders import build_register_request, unique_email
from tests.support.results import RegisterResult

_DEFAULT_NICKNAME_PATTERN = re.compile(r"^用户_\d{14,17}$")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_success_returns_201_and_token(integration_client: AsyncClient) -> None:
    """有效邮箱与密码注册成功，返回 201、token 与用户资料。"""
    email = unique_email()
    result: RegisterResult = await register_user(integration_client, email=email)

    assert result.status_code == 201
    assert result.body is not None
    assert result.body.access_token
    assert result.body.token_type == "bearer"
    assert isinstance(result.body.expires_in, int)
    assert result.body.expires_in > 0

    user = result.body.user
    assert user.email == email
    uuid.UUID(user.id)
    assert user.nickname
    assert user.created_at


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_duplicate_email_returns_422(integration_client: AsyncClient) -> None:
    """重复邮箱注册返回 422 与 detail 字段。"""
    email = unique_email()
    first: RegisterResult = await register_user(integration_client, email=email)
    assert first.status_code == 201

    response: Response = await integration_client.post(
        "/auth/register",
        json=build_register_request(email=email).model_dump(mode="json"),
    )
    assert response.status_code == 422
    body = response.json()
    assert "error" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_default_nickname_when_omitted(integration_client: AsyncClient) -> None:
    """未提供 nickname 时使用默认昵称（用户_ + 时间戳）。"""
    result: RegisterResult = await register_user(integration_client)

    assert result.status_code == 201
    assert result.body is not None
    nickname = result.body.user.nickname
    assert _DEFAULT_NICKNAME_PATTERN.match(nickname)
