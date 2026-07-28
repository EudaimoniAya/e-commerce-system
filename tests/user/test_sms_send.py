"""user 域 POST /auth/sms/send integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md）：
- 发送成功返回统一成功响应 200
- 手机号格式非法返回 422
- 日发送次数超限返回 429
"""

import pytest
from httpx import AsyncClient

from tests.support.helper.auth import send_sms_otp
from tests.support.builders import build_sms_send_request


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_valid_phone_returns_200(integration_client: AsyncClient) -> None:
    """合法手机号发送 OTP 返回 200。"""
    result = await send_sms_otp(integration_client)
    assert result.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_invalid_phone_returns_422(integration_client: AsyncClient) -> None:
    """格式非法手机号返回 422（无法规范化为 11 位）。"""
    body = build_sms_send_request(phone="not-a-phone")
    response = await integration_client.post(
        "/auth/sms/send", json=body.model_dump(mode="json"),
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_daily_limit_exceeded_returns_429(
    integration_client: AsyncClient,
) -> None:
    """日发送次数超限返回 429。"""
    phone = "13900139000"
    for _ in range(10):
        await send_sms_otp(integration_client, phone=phone)

    over_limit = await send_sms_otp(integration_client, phone=phone)
    assert over_limit.status_code == 429
