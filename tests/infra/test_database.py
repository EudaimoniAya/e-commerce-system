"""infra/database 异步 Session 依赖测试（TDD 红阶段）。"""

import allure
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("infra")
@allure.feature("database")
@allure.title("AsyncSession 可执行 SELECT 1")
async def test_get_db_select_one(database_url: str) -> None:
    """AsyncSession 可执行 SELECT 1（独立 engine，不污染全局单例）。"""
    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()
