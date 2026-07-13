"""user 域登录端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import login_user, register_user, unique_email


async def _seed_inactive_user(database_url: str, email: str, password: str) -> None:
    """向 users 表插入 is_active=false 用户（需 migration 002）。"""
    from pwdlib import PasswordHash

    user_id = str(uuid.uuid4())
    password_hash = PasswordHash.recommended().hash(password)
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO users (
                    id, email, password_hash, nickname, is_active, created_at, updated_at
                ) VALUES (
                    :id, :email, :password_hash, :nickname, 0, NOW(), NOW()
                )
                """
            ),
            {
                "id": user_id,
                "email": email,
                "password_hash": password_hash,
                "nickname": "inactive_user",
            },
        )
    await engine.dispose()


@pytest.mark.integration
def test_login_success_returns_200_and_token(client) -> None:
    """正确凭据且用户 active 时登录返回 200 与 token。"""
    email = unique_email()
    password = "password123"
    registered = register_user(client, email=email, password=password)
    assert registered["status_code"] == 201

    result = login_user(client, email=email, password=password)
    assert result["status_code"] == 200
    body = result["json"]
    assert body is not None
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0

    user = body["user"]
    assert user["email"] == email
    assert "password" not in user
    assert "password_hash" not in user


@pytest.mark.integration
def test_login_wrong_password_returns_422(client) -> None:
    """密码错误返回 422（不暴露邮箱是否存在）。"""
    email = unique_email()
    registered = register_user(client, email=email)
    assert registered["status_code"] == 201

    result = login_user(client, email=email, password="wrongpass99")
    assert result["status_code"] == 422
    body = result["json"]
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
def test_login_nonexistent_email_returns_422(client) -> None:
    """邮箱不存在返回 422（与密码错误响应形态一致）。"""
    result = login_user(client, email=unique_email("missing"))

    assert result["status_code"] == 422
    body = result["json"]
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_inactive_user_returns_403(client, database_url: str) -> None:
    """is_active=false 用户凭据正确时返回 403。"""
    email = unique_email("inactive")
    password = "password123"
    await _seed_inactive_user(database_url, email=email, password=password)

    result = login_user(client, email=email, password=password)
    assert result["status_code"] == 403
