"""infra Redis integration 测试。"""

import asyncio

import allure
import pytest
from redis.asyncio import Redis

# ── Settings 必填 REDIS_URL ──────────────────────────────────────────────────


def test_redis_url_is_required_when_missing() -> None:
    """缺少 REDIS_URL 时 Settings 构造会因字段必填而失败。

    pydantic-settings 的 model_validate 仍会读取 env 文件；通过临时
    删除系统环境变量中的 REDIS_URL 来真正测试必填校验。
    """
    import os

    from pydantic import ValidationError

    from app.infra.config import Settings

    old = os.environ.pop("REDIS_URL", None)
    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]
    finally:
        if old is not None:
            os.environ["REDIS_URL"] = old


def test_redis_url_appears_in_settings() -> None:
    """从 .env.test 加载 Settings 时 redis_url 应存在且包含 /1。"""
    from app.infra.config import get_settings

    settings = get_settings()
    assert settings.redis_url
    assert settings.redis_url.endswith("/1")


# ── Redis 客户端连通性 ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("infra")
@allure.feature("redis")
@allure.title("redis_client fixture PING 返回 True")
async def test_redis_client_ping(redis_client: Redis) -> None:
    """redis_client fixture PING 应返回 True。"""
    result = await redis_client.ping()
    assert result is True


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("infra")
@allure.feature("redis")
@allure.title("SET 后 GET 返回原值，TTL 到期 key 过期")
async def test_redis_set_get_ttl(
    redis_client: Redis,
    flush_test_redis_db: None,
) -> None:
    """SET 后 GET 应返回原值，TTL 到期后 key 应过期。"""
    await redis_client.set("test:key", "hello", ex=2)
    assert await redis_client.get("test:key") == b"hello"  # type: ignore[union-attr]

    # 轮询等待过期（避免全量 CI 负载下固定 sleep 偶发未过期）
    for _ in range(30):
        if await redis_client.get("test:key") is None:
            break
        await asyncio.sleep(0.2)
    else:
        pytest.fail("key 在 6 秒内未过期")
