"""infra/database 异步 Session 依赖测试（TDD 红阶段）。"""

import pytest
from sqlalchemy import text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_db_select_one() -> None:
    """get_db 依赖注入返回可用 AsyncSession，可执行 SELECT 1。"""
    from app.infra.database import get_db

    async for session in get_db():
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
        break
