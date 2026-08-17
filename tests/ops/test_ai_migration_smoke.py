"""AI 库 Alembic 迁移与 _infra_ai_migration_smoke 表 integration 测试（TDD 红阶段）。"""

import os
import subprocess
import sys

import allure
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_ROLLBACK_MARKER_NOTE = "ai-rollback-zero-side-effect-marker"


@pytest.fixture(scope="session")
def ai_database_url() -> str:
    """当前测试会话使用的 AI PostgreSQL 连接串（从 Settings 读取）。"""
    from app.infra.config import get_settings

    return get_settings().ai_database_url


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("ai_migration_smoke")
@allure.title("AI 库 upgrade head 后存在 vector 扩展与 smoke 表")
async def test_ai_alembic_upgrade_head_creates_smoke_table(
    ai_database_url: str,
) -> None:
    """upgrade head 后存在 pgvector 扩展、_infra_ai_migration_smoke 表与 Alembic 版本记录。"""
    env = {**os.environ, "AI_DATABASE_URL": ai_database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic_ai.ini", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    engine = create_async_engine(ai_database_url)
    async with engine.connect() as conn:
        vector_ext = await conn.scalar(
            text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")
        )
        smoke = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name = '_infra_ai_migration_smoke'"
            )
        )
        version = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name = 'alembic_version'"
            )
        )
    await engine.dispose()
    assert vector_ext == 1
    assert smoke == 1
    assert version == 1


@pytest.fixture
async def ai_db_session(ai_database_url: str) -> AsyncSession:
    """AI 库 SAVEPOINT 事务隔离 session（镜像 db_session 纪律）。"""
    engine = create_async_engine(ai_database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("ai_migration_smoke")
@allure.title("对 AI smoke 表插入含 embedding 的行并查询成功")
async def test_ai_migration_smoke_crud(ai_db_session: AsyncSession) -> None:
    """对 _infra_ai_migration_smoke 插入含 embedding 的行并查询成功（事务内可见）。"""
    from app.infra.embedder import get_embedder
    from app.infra.models.ai_migration_smoke import InfraAiMigrationSmoke

    embedder = get_embedder()
    vector = embedder.embed_texts([_ROLLBACK_MARKER_NOTE])[0]

    row = InfraAiMigrationSmoke(note=_ROLLBACK_MARKER_NOTE, embedding=vector)
    ai_db_session.add(row)
    await ai_db_session.flush()

    found = await ai_db_session.scalar(
        select(InfraAiMigrationSmoke).where(
            InfraAiMigrationSmoke.note == _ROLLBACK_MARKER_NOTE
        )
    )
    assert found is not None
    assert found.note == _ROLLBACK_MARKER_NOTE
    assert len(found.embedding) == embedder.dimension


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ops")
@allure.feature("ai_migration_smoke")
@allure.title("前序 AI smoke 测试 rollback 后标记行不可见")
async def test_ai_migration_smoke_rollback_zero_side_effect(
    ai_db_session: AsyncSession,
) -> None:
    """前序测试 rollback 后标记行对本测试不可见（零副作用）。"""
    from app.infra.models.ai_migration_smoke import InfraAiMigrationSmoke

    count = await ai_db_session.scalar(
        select(func.count())
        .select_from(InfraAiMigrationSmoke)
        .where(InfraAiMigrationSmoke.note == _ROLLBACK_MARKER_NOTE)
    )
    assert count == 0
