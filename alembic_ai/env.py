"""AI 库（PostgreSQL + pgvector）Alembic 迁移环境配置。"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# 导入模型以注册 metadata（autogenerate 用）
import app.infra.models  # noqa: F401
from alembic import context
from app.infra.ai_database import AiBase
from app.infra.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = AiBase.metadata


def get_url() -> str:
    """从应用配置读取 AI 库 asyncpg 连接串。"""
    return get_settings().ai_database_url


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL 脚本。"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：通过 async engine 执行迁移。"""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
