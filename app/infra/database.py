"""异步数据库引擎依赖、Session 与 ORM Base。"""

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


class Base(DeclarativeBase):
    """各域 ORM 模型共享的声明式基类。"""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def reset_engine() -> None:
    """释放全局 engine 并重置（测试隔离用，避免跨事件循环复用连接池）。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """懒加载 async SQLAlchemy engine。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """懒加载 AsyncSession 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求级 AsyncSession，结束时关闭连接。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        await session.close()
