"""user 域注册端点 integration 测试（TDD 红阶段）。"""

import re
import uuid

import pytest

from tests.conftest import register_user, unique_email

_USER_FIELDS = {"id", "email", "nickname", "created_at"}
_DEFAULT_NICKNAME_PATTERN = re.compile(r"^用户_\d{14,17}$")


@pytest.mark.integration
def test_register_success_returns_201_and_token(client) -> None:
    """有效邮箱与密码注册成功，返回 201、token 与用户资料。"""
    email = unique_email()
    result = register_user(client, email=email)

    assert result["status_code"] == 201
    body = result["json"]
    assert body is not None
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0

    user = body["user"]
    assert set(user.keys()) >= _USER_FIELDS
    assert user["email"] == email
    uuid.UUID(user["id"])
    assert "password" not in user
    assert "password_hash" not in user


@pytest.mark.integration
def test_register_duplicate_email_returns_422(client) -> None:
    """重复邮箱注册返回 422 与 detail 字段。"""
    email = unique_email()
    first = register_user(client, email=email)
    assert first["status_code"] == 201

    second = register_user(client, email=email)
    assert second["status_code"] == 422
    body = second["json"]
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
def test_register_password_too_short_returns_422(client) -> None:
    """密码长度小于 8 返回 422。"""
    result = register_user(client, password="short")

    assert result["status_code"] == 422


@pytest.mark.integration
def test_register_password_too_long_returns_422(client) -> None:
    """密码长度大于 32 返回 422。"""
    result = register_user(client, password="a" * 33)

    assert result["status_code"] == 422


@pytest.mark.integration
def test_register_default_nickname_when_omitted(client) -> None:
    """未提供 nickname 时使用默认昵称（用户_ + 时间戳）。"""
    result = register_user(client)

    assert result["status_code"] == 201
    body = result["json"]
    assert body is not None
    nickname = body["user"]["nickname"]
    assert _DEFAULT_NICKNAME_PATTERN.match(nickname)
