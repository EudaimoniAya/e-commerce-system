"""AI 域组合根：仅装配类（无 router / 无 get_current_*）。

CLI 与测试以普通函数调用；将来若有 AI HTTP，同一函数可挂 ``Depends``。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.config import get_settings
from app.media.deps import get_media_service, get_storage_backend
from app.media.service import MediaService


def build_media_service(session: AsyncSession) -> MediaService:
    """装配 MediaService：经 media 域 service-provider + storage backend。"""
    return get_media_service(
        session=session,
        storage=get_storage_backend(get_settings()),
    )
