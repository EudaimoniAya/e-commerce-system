"""infra AI PostgreSQL + pgvector integration 测试（TDD 红阶段）。"""

import os

import allure
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def test_ai_database_url_is_required_when_missing() -> None:
    """缺少 AI_DATABASE_URL 时 Settings 构造会因字段必填而失败。"""
    from app.infra.config import Settings

    assert "ai_database_url" in Settings.model_fields, (
        "Settings 尚未定义 ai_database_url（Task 2 实现）"
    )

    old = os.environ.pop("AI_DATABASE_URL", None)
    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]
    finally:
        if old is not None:
            os.environ["AI_DATABASE_URL"] = old


def test_ai_database_url_appears_in_settings() -> None:
    """从 .env.test 加载 Settings 时 ai_database_url 应存在且指向 test AI 库。"""
    from app.infra.config import get_settings

    settings = get_settings()
    assert settings.ai_database_url
    assert "ecommerce_ai_test" in settings.ai_database_url


@pytest.fixture(scope="session")
def ai_database_url() -> str:
    """当前测试会话使用的 AI PostgreSQL 连接串（从 Settings 读取）。"""
    from app.infra.config import get_settings

    return get_settings().ai_database_url


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("infra")
@allure.feature("pg")
@allure.title("AI AsyncSession 可执行 SELECT 1")
async def test_ai_database_select_one(ai_database_url: str) -> None:
    """经 infra AI 客户端或独立 engine 执行 SELECT 1 成功。"""
    from app.infra.ai_database import get_ai_engine

    engine = get_ai_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("infra")
@allure.feature("pg")
@allure.title("MockEmbedder 向量写入后 pgvector 相似度检索 top-1 命中")
async def test_pgvector_similarity_smoke(ai_database_url: str) -> None:
    """MockEmbedder 生成向量 → 写入 smoke 表 → 相似度查询 top-1 命中。"""
    from app.infra.embedder import get_embedder

    embedder = get_embedder()
    note_target = "pg-smoke-target"
    note_other = "pg-smoke-other"
    vec_target = embedder.embed_texts([note_target])[0]
    vec_other = embedder.embed_texts([note_other])[0]
    query_vec = embedder.embed_texts([note_target])[0]

    engine = create_async_engine(ai_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO _infra_ai_migration_smoke (id, note, embedding) "
                "VALUES (gen_random_uuid(), :note, :embedding)"
            ),
            {"note": note_target, "embedding": str(vec_target)},
        )
        await conn.execute(
            text(
                "INSERT INTO _infra_ai_migration_smoke (id, note, embedding) "
                "VALUES (gen_random_uuid(), :note, :embedding)"
            ),
            {"note": note_other, "embedding": str(vec_other)},
        )
        top_note = await conn.scalar(
            text(
                "SELECT note FROM _infra_ai_migration_smoke "
                "ORDER BY embedding <=> CAST(:query AS vector) "
                "LIMIT 1"
            ),
            {"query": str(query_vec)},
        )
    await engine.dispose()
    assert top_note == note_target
