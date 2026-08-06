"""media 域 ORM 模型：MediaAsset。

``media_assets`` 存储上传文件的元数据，字节由 ``StorageBackend`` 管理。
storage_key 格式：``{id[:2]}/{id[2:4]}/{id}``（两级分片降低单目录文件数）。
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class MediaAsset(Base):
    """映射 ``media_assets`` 表——上传媒体文件元数据。

    列（8 列）：
    - id: UUID v4 PK
    - owner_user_id: FK → users.id
    - visibility: owner_only | public，默认 owner_only
    - content_type: 魔数检测后的 MIME
    - size_bytes: 实际上传字节数
    - storage_key: StorageBackend 内对象键（两级分片路径）
    - original_filename: 客户端上传文件名
    - created_at: 创建时间
    """

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(
        String(16),
        default="owner_only",
        server_default="owner_only",
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=func.now(),
    )
