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
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=True,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "unavailable", "redis": "ok", "postgresql": "ok"},
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
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=True,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"mysql": "ok", "redis": "ok", "postgresql": "ok"},
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
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=True,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "ok", "redis": "unavailable", "postgresql": "ok"},
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
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=True,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "mysql": "unavailable",
            "redis": "unavailable",
            "postgresql": "ok",
        },
    }


# ── PostgreSQL readiness 扩展（TDD 红阶段：is_postgresql_ready 与三库聚合尚不完整）──


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("MySQL、Redis 与 PostgreSQL 均可用时 /health/ready 返回 200")
async def test_readiness_returns_200_when_all_three_ok(client: AsyncClient) -> None:
    """三库均可用时 GET /health/ready 返回 200 与三 ok。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=True),
        patch("app.infra.readiness.service.is_redis_ready", return_value=True),
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=True,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"mysql": "ok", "redis": "ok", "postgresql": "ok"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("PostgreSQL 不可用且 MySQL/Redis 可用时 /health/ready 返回 503")
async def test_readiness_returns_503_when_postgresql_unavailable(
    client: AsyncClient,
) -> None:
    """PostgreSQL 不可用且 MySQL/Redis 可用时 GET /health/ready 返回 503。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=True),
        patch("app.infra.readiness.service.is_redis_ready", return_value=True),
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=False,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mysql": "ok", "redis": "ok", "postgresql": "unavailable"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("三库均不可用时 /health/ready 返回 503")
async def test_readiness_returns_503_when_all_three_unavailable(
    client: AsyncClient,
) -> None:
    """MySQL、Redis 与 PostgreSQL 均不可用时 GET /health/ready 返回 503。"""
    with (
        patch("app.infra.readiness.service.is_mysql_ready", return_value=False),
        patch("app.infra.readiness.service.is_redis_ready", return_value=False),
        patch(
            "app.infra.readiness.service.is_postgresql_ready",
            return_value=False,
            create=True,
        ),
    ):
        response: Response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "mysql": "unavailable",
            "redis": "unavailable",
            "postgresql": "unavailable",
        },
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("readiness checks 包含 postgresql 键")
async def test_readiness_checks_include_postgresql(client: AsyncClient) -> None:
    """GET /health/ready 响应 checks SHALL 包含 postgresql 键。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code in (200, 503)
    checks = response.json()["checks"]
    assert "postgresql" in checks
    assert checks["postgresql"] in ("ok", "unavailable")


# ── 真实探测路径（不经 mock；需 MySQL/Redis/PG 三库就绪）────────────────────────


@pytest.mark.integration
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("真实 PostgreSQL 探测：PG 就绪时 is_postgresql_ready 为 True")
def test_is_postgresql_ready_true_when_pg_up() -> None:
    """PG 就绪时 is_postgresql_ready() 返回 True（sync 入口，无 running loop → asyncio.run 分支）。"""
    from app.infra.readiness.service import is_postgresql_ready

    assert is_postgresql_ready() is True


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("真实 PostgreSQL 探测：不可达时 is_postgresql_ready 为 False")
async def test_is_postgresql_ready_false_when_pg_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_DATABASE_URL 指向不可达端口时 is_postgresql_ready() 返回 False（ThreadPoolExecutor 分支）。"""
    from app.infra.config import get_settings
    from app.infra.readiness.service import is_postgresql_ready

    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "ai_database_url",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:1/nonexistent",
    )

    assert is_postgresql_ready() is False


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("readiness")
@allure.title("三库真实就绪时 /health/ready 返回 200（不经 mock）")
async def test_readiness_returns_200_with_all_real_deps(
    client: AsyncClient,
) -> None:
    """MySQL、Redis 与 PostgreSQL 真实就绪时 GET /health/ready 返回 200 与三 ok。"""
    response: Response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"mysql": "ok", "redis": "ok", "postgresql": "ok"},
    }
