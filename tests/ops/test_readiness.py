"""运维就绪探针端点测试（ops）。"""

from unittest.mock import patch

import allure
import pytest
from httpx import AsyncClient, Response


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("MySQL 可用时 /health/ready 返回 200")
async def test_readiness_returns_200_when_mysql_ok(client: AsyncClient) -> None:
    """MySQL 可用时 GET /health/ready 返回 200 与 ready 响应体（checks 含 redis）。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["mysql"] == "ok"
    # redis 也参与 readiness；当 Redis 在线时 checks.redis 为 ok
    assert "redis" in body["checks"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("MySQL 不可用时 /health/ready 返回 503")
async def test_readiness_returns_503_when_mysql_unavailable(
    client: AsyncClient,
) -> None:
    """MySQL 不可用时 GET /health/ready 返回 503 与 not_ready（checks 仍含 redis）。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=False),
        patch("app.infra.readiness.service.is_redis_ready", return_value=True),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "unavailable", "redis": "ok"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("GET /health/ready Content-Type 包含 application/json")
async def test_readiness_content_type_is_json(client: AsyncClient) -> None:
    """GET /health/ready 响应 Content-Type 包含 application/json。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code in (200, 503)
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type


# ── Redis readiness 扩展（TDD 红阶段：is_redis_ready 尚不存在）──────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("MySQL 与 Redis 均可用时 /health/ready 返回 200")
async def test_readiness_returns_200_when_mysql_and_redis_both_ok(
    client: AsyncClient,
) -> None:
    """MySQL 与 Redis 均可用时 GET /health/ready 返回 200 与双 ok。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=True),
        patch("app.infra.readiness.service.is_redis_ready", return_value=True),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"mysql": "ok", "redis": "ok"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("Redis 不可用且 MySQL 可用时 /health/ready 返回 503")
async def test_readiness_returns_503_when_redis_unavailable(
    client: AsyncClient,
) -> None:
    """Redis 不可用且 MySQL 可用时 GET /health/ready 返回 503。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=True),
        patch("app.infra.readiness.service.is_redis_ready", return_value=False),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "ok", "redis": "unavailable"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("MySQL 与 Redis 均不可用时 /health/ready 返回 503")
async def test_readiness_returns_503_when_both_unavailable(
    client: AsyncClient,
) -> None:
    """MySQL 与 Redis 均不可用时 GET /health/ready 返回 503。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=False),
        patch("app.infra.readiness.service.is_redis_ready", return_value=False),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "unavailable", "redis": "unavailable"},
    }
