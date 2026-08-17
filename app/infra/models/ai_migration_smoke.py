"""AI 库 Alembic 迁移管线验证用 infra 表 ORM。"""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.ai_database import AiBase

# migration 001 与 Settings.embedding_dimension 均钉在 1024；
# 变更维度须新 revision + 全量 reindex（见 infra-ai-pgvector design Decision 4/6）。
_EMBEDDING_DIMENSION = 1024


class InfraAiMigrationSmoke(AiBase):
    """映射 `_infra_ai_migration_smoke` 表，仅用于 infra AI 库集成测试。"""

    __tablename__ = "_infra_ai_migration_smoke"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    note: Mapped[str] = mapped_column(String(255))
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIMENSION))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
