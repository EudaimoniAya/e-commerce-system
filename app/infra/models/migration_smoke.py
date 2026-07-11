"""Alembic 迁移管线验证用 infra 表 ORM。"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class InfraMigrationSmoke(Base):
    """映射 `_infra_migration_smoke` 表，仅用于 infra 集成测试。"""

    __tablename__ = "_infra_migration_smoke"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    note: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
