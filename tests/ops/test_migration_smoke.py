"""Alembic 迁移与 _infra_migration_smoke 表 integration 测试（TDD 红阶段）。"""

import os
import subprocess
import sys

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

# 用于验证 transaction rollback 零副作用的标记行
_ROLLBACK_MARKER_NOTE = "rollback-zero-side-effect-marker"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alembic_upgrade_head_creates_smoke_table(database_url: str) -> None:
    """upgrade head 后存在 _infra_migration_smoke 表与 Alembic 版本记录。"""
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        smoke = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() "
                "AND table_name = '_infra_migration_smoke'"
            )
        )
        version = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'alembic_version'"
            )
        )
    await engine.dispose()
    assert smoke == 1
    assert version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_smoke_crud(db_session) -> None:
    """对 _infra_migration_smoke 插入并查询成功（事务内可见）。"""
    from app.infra.models.migration_smoke import InfraMigrationSmoke

    row = InfraMigrationSmoke(note=_ROLLBACK_MARKER_NOTE)
    db_session.add(row)
    await db_session.flush()

    found = await db_session.scalar(
        select(InfraMigrationSmoke).where(
            InfraMigrationSmoke.note == _ROLLBACK_MARKER_NOTE
        )
    )
    assert found is not None
    assert found.note == _ROLLBACK_MARKER_NOTE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_smoke_rollback_zero_side_effect(db_session) -> None:
    """前序测试 rollback 后标记行对本测试不可见（零副作用）。"""
    from app.infra.models.migration_smoke import InfraMigrationSmoke

    count = await db_session.scalar(
        select(func.count())
        .select_from(InfraMigrationSmoke)
        .where(InfraMigrationSmoke.note == _ROLLBACK_MARKER_NOTE)
    )
    assert count == 0
