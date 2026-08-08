"""user 域 ORM 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class User(Base):
    """映射 `users` 表。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_media_id: Mapped[uuid.UUID | None] = mapped_column(
        String(36),
        ForeignKey("media_assets.id"),
        nullable=True,
    )
    nickname: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
