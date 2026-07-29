"""readiness 业务逻辑（MySQL + Redis 连通性检查）。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.infra.config import get_settings


async def _ping_mysql() -> bool:
    """使用独立 engine 执行 SELECT 1，避免与全局 engine 跨事件循环冲突。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


def is_mysql_ready() -> bool:
    """同步入口：检查 MySQL 是否就绪（供路由与测试 mock 使用）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_ping_mysql())

    # pytest-asyncio 等场景下已有事件循环，在线程中运行独立 loop
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, _ping_mysql()).result()


async def _ping_redis() -> bool:
    """使用独立短连接 ping Redis，避免与全局 pool 跨事件循环冲突。"""
    settings = get_settings()
    r = aioredis.from_url(settings.redis_url)
    try:
        return await r.ping()
    except Exception:
        return False
    finally:
        await r.aclose()


def is_redis_ready() -> bool:
    """同步入口：检查 Redis 是否就绪（供路由与测试 mock 使用）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_ping_redis())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, _ping_redis()).result()
