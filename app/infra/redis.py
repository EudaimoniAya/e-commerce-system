"""Async Redis 客户端、连接池与 FastAPI 依赖。

与 database.py 同模式：模块级懒加载单例 + reset 用于测试隔离。
业务域 SHALL NOT 自行 ``Redis.from_url``；仅通过本模块获取客户端。
"""

import redis.asyncio as aioredis

from app.infra.config import get_settings

_redis: aioredis.Redis | None = None


async def reset_redis() -> None:
    """释放全局 Redis 连接并重置（测试隔离用，避免跨事件循环复用连接）。"""
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


def get_redis() -> aioredis.Redis:
    """懒加载 async Redis 客户端（连接池复用）。

    Returns:
        ``redis.asyncio.Redis`` 实例（连接池由 redis-py 内部管理）。

    Usage::

        from app.infra.redis import get_redis
        r = get_redis()
        await r.ping()
    """
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis_url)
    return _redis
