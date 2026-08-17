"""AI 读库（PostgreSQL + pgvector）异步数据库引擎依赖、Session 与 ORM Base。"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.infra.config import get_settings


class AiBase(DeclarativeBase):
    """AI 读库 ORM 模型共享的声明式基类（与 MySQL ``Base`` 分离）。"""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


_ai_engine: AsyncEngine | None = None
_ai_session_factory: async_sessionmaker[AsyncSession] | None = None


async def reset_ai_engine() -> None:
    """释放全局 AI engine 并重置（测试隔离用，避免跨事件循环复用连接池）。"""
    global _ai_engine, _ai_session_factory
    if _ai_engine is not None:
        await _ai_engine.dispose()
    _ai_engine = None
    _ai_session_factory = None


def get_ai_engine() -> AsyncEngine:
    """懒加载 async PostgreSQL（AI 读库）engine。"""
    global _ai_engine
    if _ai_engine is None:
        settings = get_settings()
        _ai_engine = create_async_engine(settings.ai_database_url)
    return _ai_engine


def get_ai_session_factory() -> async_sessionmaker[AsyncSession]:
    """懒加载 AI 读库 AsyncSession 工厂。"""
    global _ai_session_factory
    if _ai_session_factory is None:
        _ai_session_factory = async_sessionmaker(
            get_ai_engine(),
            expire_on_commit=False,
        )
    return _ai_session_factory


async def get_ai_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求级 AI 读库 AsyncSession，结束时关闭连接。"""
    session = get_ai_session_factory()()
    try:
        yield session
    finally:
        await session.close()
