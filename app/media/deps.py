"""media 域 FastAPI 依赖：storage backend、service。"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.config import Settings, get_settings
from app.infra.database import get_db
from app.media.repository import MediaRepository
from app.media.service import MediaService
from app.media.storage.local import LocalFilesystemBackend
from app.media.storage.memory import InMemoryBackend
from app.media.storage.protocol import StorageBackend


def get_storage_backend(
    settings: Settings = Depends(get_settings),
) -> StorageBackend:
    """按配置返回 StorageBackend 实例。

    - ``local``：LocalFilesystemBackend（落盘 MEDIA_STORAGE_ROOT）
    - ``memory``：InMemoryBackend（进程内，测试用）
    """
    if settings.media_storage_backend == "memory":
        return InMemoryBackend()
    return LocalFilesystemBackend(root=settings.media_storage_root)


def get_media_service(
    session: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
) -> MediaService:
    """构造 MediaService 实例，注入 DB session 与 storage backend。"""
    return MediaService(
        storage=storage,
        repository=MediaRepository(session),
    )
