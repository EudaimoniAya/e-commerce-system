"""ai 域测试公共 fixture（红阶段）。

- ``ai_database_url``：AI PG 连接串（对齐 Change 1 tests/ops、tests/infra 同名 fixture）。
- ``clean_ai_chunks``：integration 测试前后清空 ``product_embedding_chunks``，
  避免 reindex（经全局 AI session factory 真实写入）跨用例残留；表尚不存在（002 未建）时静默跳过。
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.media.service import MediaService

_CHUNKS_TABLE = "product_embedding_chunks"


@pytest.fixture(scope="session")
def ai_database_url() -> str:
    """当前测试会话使用的 AI PostgreSQL 连接串（从 Settings 读取）。"""
    from app.infra.config import get_settings

    return get_settings().ai_database_url


@pytest.fixture
async def clean_ai_chunks(ai_database_url: str) -> AsyncIterator[None]:
    """integration 测试前后清空 product_embedding_chunks（表未建时容忍）。"""
    engine = create_async_engine(ai_database_url)

    async def _purge() -> None:
        async with engine.begin() as conn:
            try:
                await conn.execute(text(f"DELETE FROM {_CHUNKS_TABLE}"))
            except Exception:
                pass  # 表尚不存在（002 未应用）——红阶段容忍

    await _purge()
    try:
        yield
    finally:
        await _purge()
    await engine.dispose()


@pytest.fixture
def media_service(db_session: AsyncSession) -> MediaService:
    """经 ``app.ai.deps.build_media_service`` 装配（测试环境 storage=memory）。"""
    from app.ai.deps import build_media_service

    return build_media_service(db_session)


@pytest.fixture(autouse=True)
async def _reset_intent_controller_override(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """integration 测试前后清理 ``build_intent_controller`` dependency override。

    红阶段 ``build_intent_controller`` 尚未改名 → 清理容忍导入缺失；
    ``tests/ai/integration/`` 的 replies 用例经 override 注入测试 controller。
    """
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    from tests.ai.testkit.pipeline import clear_intent_controller_override

    clear_intent_controller_override()
    yield
    clear_intent_controller_override()

