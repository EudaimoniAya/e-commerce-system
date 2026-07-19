"""infra/readiness 聚合探针端点测试（TDD 红阶段）。"""

from unittest.mock import patch

import pytest
from httpx import Response


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readiness_returns_200_when_mysql_ok(client) -> None:
    """MySQL 可用时 GET /health/ready 返回 200 与 ready 响应体。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"mysql": "ok"}}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readiness_returns_503_when_mysql_unavailable(client) -> None:
    """MySQL 不可用时 GET /health/ready 返回 503 与 not_ready 响应体。"""
    with patch(
        "app.infra.readiness.service.is_mysql_ready",
        return_value=False,
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "unavailable"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readiness_content_type_is_json(client) -> None:
    """GET /health/ready 响应 Content-Type 包含 application/json。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code in (200, 503)
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type
