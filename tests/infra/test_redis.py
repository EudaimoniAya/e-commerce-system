"""infra Redis integration 测试。

TDD 红阶段：``app/infra/redis.py`` 尚未创建——预期 import 失败。
"""

import pytest
from httpx import AsyncClient


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
    # redis_url 是必填字段；load 成功即证明存在
    assert settings.redis_url
    assert settings.redis_url.endswith("/1")


# ── Redis 客户端连通性 ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_client_ping(redis_client) -> None:  # type: ignore[no-untyped-def]
    """redis_client fixture PING 应返回 True。"""
    result = await redis_client.ping()
    assert result is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_set_get_ttl(
    redis_client, flush_test_redis_db  # type: ignore[no-untyped-def]  # noqa: F811
) -> None:
    """SET 后 GET 应返回原值，TTL 到期后 key 应过期。"""
    await redis_client.set("test:key", "hello", ex=2)
    assert await redis_client.get("test:key") == b"hello"  # type: ignore[union-attr]

    import asyncio

    await asyncio.sleep(3)
    assert await redis_client.get("test:key") is None
