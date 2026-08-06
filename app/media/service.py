"""media 域 Service 层：upload / delete / get_file_stream / can_read。

写入顺序：先 save 字节到 storage，后 INSERT media_assets；
若 DB 写入失败，best-effort 补偿 delete storage 字节（孤儿文件 GC 为 Non-goal）。
"""

import uuid
from datetime import datetime, timezone

from app.media.models import MediaAsset
from app.media.repository import MediaRepository
from app.media.schemas import MediaSummary
from app.media.storage.protocol import StorageBackend


class MediaService:
    """媒体资产 Service。

    Args:
        storage: StorageBackend 实例。
        repository: MediaRepository（DB 会话注入）；None 时使用进程内 dict
                    （仅限单元测试——此时无 DB 依赖）。
    """

    def __init__(
        self,
        storage: StorageBackend,
        repository: MediaRepository | None = None,
    ) -> None:
        self._repo = repository
        self._storage = storage
        # 内存后备存储：当未注入 repository 时（单元测试场景），
        # 用进程内 dict 保存 MediaAsset 元数据
        self._assets: dict[uuid.UUID, MediaAsset] = {}

    # ── public API ────────────────────────────────────────────────────────

    async def upload(
        self,
        file_bytes: bytes,
        original_filename: str,
        owner_user_id: str,
        visibility: str = "owner_only",
    ) -> MediaSummary:
        """上传文件：生成 id → save 字节 → INSERT 元数据。

        DB 写入失败时 best-effort 补偿 delete storage 字节。
        """
        media_id = uuid.uuid4()
        storage_key = _make_storage_key(media_id)
        content_type = "image/png"  # 实际由 router 经 validate_media_upload 注入

        await self._storage.save(storage_key, file_bytes)

        asset = MediaAsset(
            id=media_id,
            owner_user_id=uuid.UUID(owner_user_id),
            visibility=visibility,
            content_type=content_type,
            size_bytes=len(file_bytes),
            storage_key=storage_key,
            original_filename=original_filename,
        )
        try:
            await self._persist(asset)
        except Exception:
            await self._storage.delete(storage_key)
            raise

        return MediaSummary(
            id=str(media_id),
            url=f"/media/{media_id}/file",
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            created_at=datetime.now(timezone.utc),
        )

    async def get_file_stream(self, media_id: str) -> tuple[bytes, str]:
        """从 storage 读取文件字节与 content_type。

        Returns:
            (bytes, content_type) — 字节 + 持久化的 MIME 类型。
        """
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            raise FileNotFoundError(media_id)
        data = await self._storage.open(asset.storage_key)
        return data, asset.content_type

    async def delete(self, media_id: str) -> None:
        """删除媒体资产：DB 行 → storage 字节。"""
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            raise FileNotFoundError(media_id)
        await self._remove(asset.id)
        await self._storage.delete(asset.storage_key)

    async def can_read(
        self,
        media_id: str,
        user_id: str | None = None,
    ) -> bool:
        """判断请求者是否可读该 media。

        - ``public`` → 任何人可读
        - ``owner_only`` → 仅 owner_user_id 可读（含匿名 None → False）
        """
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            return False
        if asset.visibility == "public":
            return True
        # owner_only
        if user_id is None:
            return False
        return str(asset.owner_user_id) == user_id

    # ── 内部：双路径（DB repository 或进程内 dict）───────────────────────

    async def _persist(self, asset: MediaAsset) -> None:
        """INSERT media_assets。"""
        if self._repo is not None:
            await self._repo.insert(asset)
        else:
            self._assets[asset.id] = asset

    async def _load(self, media_id: uuid.UUID) -> MediaAsset | None:
        """SELECT by id。"""
        if self._repo is not None:
            return await self._repo.get_by_id(media_id)
        return self._assets.get(media_id)

    async def _remove(self, media_id: uuid.UUID) -> None:
        """DELETE by id。"""
        if self._repo is not None:
            await self._repo.delete_by_id(media_id)
        else:
            self._assets.pop(media_id, None)


def _make_storage_key(media_id: uuid.UUID) -> str:
    """生成两级分片 storage_key：``{hex[:2]}/{hex[2:4]}/{hex}``。"""
    hex_id = media_id.hex
    return f"{hex_id[:2]}/{hex_id[2:4]}/{hex_id}"
