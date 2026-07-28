"""user 域 POST /auth/login 手机号+密码登录 integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md MODIFIED Requirement）：
- identifier+password 正确且 active → 200
- 凭据无效（用户不存在 / 密码错 / password_hash NULL）→ 422 + INVALID_CREDENTIALS
- 用户已禁用 → 403
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.helper.auth import login_user, register_user_via_otp
from tests.support.builders import build_login_request
from tests.support.db.user import seed_inactive_user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_success_returns_200_and_token(
    integration_client: AsyncClient,
) -> None:
    """正确手机号 + 密码且 active 时登录返回 200 与 token。"""
    registered = await register_user_via_otp(integration_client)
    assert registered.status_code == 201

    result = await login_user(
        integration_client,
        identifier=registered.phone,
        password=registered.password,
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body.access_token
    assert result.body.token_type == "bearer"
    assert result.body.expires_in > 0

    user = result.body.user
    assert user.phone == registered.phone


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_wrong_password_returns_422(
    integration_client: AsyncClient,
) -> None:
    """密码错误返回 422（不暴露是否存在）。"""
    registered = await register_user_via_otp(integration_client)
    assert registered.status_code == 201

    response = await integration_client.post(
        "/auth/login",
        json=build_login_request(
            identifier=registered.phone, password="wrongpass99"
        ).model_dump(mode="json"),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_nonexistent_phone_returns_422(
    integration_client: AsyncClient,
) -> None:
    """手机号不存在返回 422（与密码错误响应一致）。"""
    response = await integration_client.post(
        "/auth/login",
        json=build_login_request(identifier="13800138000").model_dump(
            mode="json"
        ),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_inactive_user_returns_403(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """is_active=false 用户凭据正确时返回 403。"""
    phone = "13800138000"
    password = "password123"
    await seed_inactive_user(
        db_session, email=f"{phone}@example.com", password=password,
    )

    result = await login_user(
        integration_client, identifier=phone, password=password,
    )
    assert result.status_code == 403
    assert result.body is None
