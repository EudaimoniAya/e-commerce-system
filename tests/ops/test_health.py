"""运维存活探针端点测试（ops）。"""

import allure
import pytest
from httpx import AsyncClient, Response


@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("health")
@allure.title("GET /health 返回 200 与 ok status")
async def test_health_returns_200_with_ok_status(client: AsyncClient) -> None:
    """GET /health 在服务正常时返回 200 与 {"status": "ok"}。"""
    response: Response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("health")
@allure.title("GET /health Content-Type 包含 application/json")
async def test_health_content_type_is_json(client: AsyncClient) -> None:
    """GET /health 响应 Content-Type 包含 application/json。"""
    response: Response = await client.get("/health")

    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type
