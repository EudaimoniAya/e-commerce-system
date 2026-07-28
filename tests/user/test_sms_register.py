"""user 域 POST /auth/sms/register integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md）：
- 新用户注册成功返回 201 与 token
- 手机号已注册返回 422
- 注册缺少 password 或长度不合规返回 422
- OTP 错误或过期返回 422
- 未提供昵称时使用默认昵称
- 注册验证失败次数超限返回 429
"""

import re
import uuid

import allure
import pytest
from httpx import AsyncClient

from tests.support.helper.auth import register_user_via_otp
from tests.support.builders import build_sms_register_request

_DEFAULT_NICKNAME_PATTERN = re.compile(r"^用户_\d{14,17}$")


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("新用户合法 OTP + password 注册成功，返回 201 与 token。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_success_returns_201_and_token(
    integration_client: AsyncClient,
) -> None:
    """新用户合法 OTP + password 注册成功，返回 201 与 token。"""
    result = await register_user_via_otp(integration_client)

    assert result.status_code == 201
    assert result.body is not None
    assert result.body.access_token
    assert result.body.token_type == "bearer"
    assert isinstance(result.body.expires_in, int)
    assert result.body.expires_in > 0

    user = result.body.user
    assert user.phone == result.phone
    uuid.UUID(user.id)
    assert user.nickname


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("手机号已注册时返回 422。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_phone_already_exists_returns_422(
    integration_client: AsyncClient,
) -> None:
    """手机号已注册时返回 422。"""
    first = await register_user_via_otp(integration_client)
    assert first.status_code == 201

    second = await register_user_via_otp(integration_client, phone=first.phone)
    assert second.status_code == 422


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("缺少 password 返回 422。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_without_password_returns_422(
    integration_client: AsyncClient,
) -> None:
    """缺少 password 返回 422。"""
    response = await integration_client.post(
        "/auth/sms/register",
        json={"phone": "13800138000", "code": "123456"},
    )
    assert response.status_code == 422


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("OTP 错误返回 422。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_wrong_otp_returns_422(
    integration_client: AsyncClient,
) -> None:
    """OTP 错误返回 422。"""
    phone = "13800138000"
    body = build_sms_register_request(phone=phone, code="000000")
    response = await integration_client.post(
        "/auth/sms/register", json=body.model_dump(mode="json"),
    )
    assert response.status_code == 422

    err = response.json()
    assert "Invalid or expired verification code" in str(err)


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("未提供 nickname 时使用默认昵称。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_default_nickname_when_omitted(
    integration_client: AsyncClient,
) -> None:
    """未提供 nickname 时使用默认昵称。"""
    result = await register_user_via_otp(integration_client, nickname=None)
    assert result.status_code == 201
    assert result.body is not None
    assert _DEFAULT_NICKNAME_PATTERN.match(result.body.user.nickname)


@allure.epic("user")
@allure.feature("sms_register")
@allure.title("OTP 验证失败超上限返回 429。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_exceed_fail_limit_returns_429(
    integration_client: AsyncClient,
) -> None:
    """OTP 验证失败超上限返回 429。"""
    phone = "13800138001"
    for _ in range(5):
        body = build_sms_register_request(phone=phone, code="000000")
        await integration_client.post(
            "/auth/sms/register", json=body.model_dump(mode="json"),
        )

    final = build_sms_register_request(phone=phone, code="000000")
    response = await integration_client.post(
        "/auth/sms/register", json=final.model_dump(mode="json"),
    )
    assert response.status_code == 429
