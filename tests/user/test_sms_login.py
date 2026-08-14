"""user 域 POST /auth/sms/login integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md）：
- 已有用户 OTP 登录成功返回 200
- 用户不存在返回 422（与 OTP 错误同文案）
- OTP 错误或过期返回 422
- 用户已禁用返回 403
- OTP 验证失败次数超限返回 429
"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.builders import build_sms_login_request, unique_phone
from tests.testkit.db.user import seed_inactive_user
from tests.testkit.helper.auth import login_user_via_otp, register_user_via_otp


@allure.epic("user")
@allure.feature("sms_login")
@allure.title("已有用户 OTP 登录成功返回 200 与 token。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_success_returns_200_and_token(
    integration_client: AsyncClient,
) -> None:
    """已有用户 OTP 登录成功返回 200 与 token。"""
    registered = await register_user_via_otp(integration_client)
    assert registered.status_code == 201

    result = await login_user_via_otp(integration_client, phone=registered.phone)
    assert result.status_code == 200
    assert result.body is not None
    assert result.body.access_token
    assert result.body.token_type == "bearer"
    assert isinstance(result.body.expires_in, int)
    assert result.body.expires_in > 0

    user = result.body.user
    assert user.phone == registered.phone
    uuid.UUID(user.id)


@allure.epic("user")
@allure.feature("sms_login")
@allure.title("不存在手机号返回 422（与 OTP 错误同文案，防枚举）。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_nonexistent_phone_returns_422(
    integration_client: AsyncClient,
) -> None:
    """不存在手机号返回 422（与 OTP 错误同文案，防枚举）。"""
    body = build_sms_login_request(phone="13800138000")
    response = await integration_client.post(
        "/auth/sms/login",
        json=body.model_dump(mode="json"),
    )
    assert response.status_code == 422
    err = response.json()
    assert "Invalid or expired verification code" in str(err)


@allure.epic("user")
@allure.feature("sms_login")
@allure.title("OTP 错误返回 422。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_wrong_otp_returns_422(
    integration_client: AsyncClient,
) -> None:
    """OTP 错误返回 422。"""
    registered = await register_user_via_otp(integration_client)
    assert registered.status_code == 201

    body = build_sms_login_request(phone=registered.phone, code="000000")
    response = await integration_client.post(
        "/auth/sms/login",
        json=body.model_dump(mode="json"),
    )
    assert response.status_code == 422
    err = response.json()
    assert "Invalid or expired verification code" in str(err)


@allure.epic("user")
@allure.feature("sms_login")
@allure.title("is_active=false 用户 OTP 登录返回 403。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_disabled_user_returns_403(
    integration_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """is_active=false 用户 OTP 登录返回 403。"""
    phone = unique_phone()
    password = "password123"
    await seed_inactive_user(
        db_session,
        email=f"{phone}@example.com",
        password=password,
        phone=phone,
    )

    result = await login_user_via_otp(integration_client, phone=phone)
    assert result.status_code == 403
    assert result.body is None


@allure.epic("user")
@allure.feature("sms_login")
@allure.title("OTP 验证失败超上限返回 429。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_exceed_fail_limit_returns_429(
    integration_client: AsyncClient,
) -> None:
    """OTP 验证失败超上限返回 429。"""
    phone = "13800138002"
    for _ in range(5):
        body = build_sms_login_request(phone=phone, code="000000")
        await integration_client.post(
            "/auth/sms/login",
            json=body.model_dump(mode="json"),
        )

    final = build_sms_login_request(phone=phone, code="000000")
    response = await integration_client.post(
        "/auth/sms/login",
        json=final.model_dump(mode="json"),
    )
    assert response.status_code == 429
