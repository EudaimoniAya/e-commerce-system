"""已移除的注册端点返回 404 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md）：
- 旧 `/auth/register` 返回 404
- 旧 `/auth/sms/verify`（已拆分为 register/login）返回 404
"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.builders import build_register_request


@allure.epic("user")
@allure.feature("register")
@allure.title("POST /auth/register 已移除，返回 404。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_old_register_endpoint_returns_404(
    integration_client: AsyncClient,
) -> None:
    """POST /auth/register 已移除，返回 404。"""
    response = await integration_client.post(
        "/auth/register",
        json=build_register_request().model_dump(mode="json"),
    )
    assert response.status_code == 404


@allure.epic("user")
@allure.feature("register")
@allure.title("POST /auth/sms/verify 已拆分为 register/login，返回 404。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_old_sms_verify_endpoint_returns_404(
    integration_client: AsyncClient,
) -> None:
    """POST /auth/sms/verify 已拆分为 register/login，返回 404。"""
    response = await integration_client.post(
        "/auth/sms/verify",
        json={"phone": "13800138000", "code": "123456"},
    )
    assert response.status_code == 404
