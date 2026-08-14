"""media 域 Service 层：upload / get_detail / delete / get_file_stream / can_read。

写入顺序：先 save 字节到 storage，后 INSERT media_assets；
若 DB 写入失败，best-effort 补偿 delete storage 字节（孤儿文件 GC 为 Non-goal）。

attach 支撑方法（供 user/catalog 跨域调用）：assert_owned_by / assert_image_content_type /
mark_public / resolve_urls / count_references。
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.media.models import MediaAsset
from app.media.repository import MediaRepository
from app.media.schemas import MediaDetail, MediaSummary
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
        content_type: str,
        visibility: str = "owner_only",
    ) -> MediaSummary:
        """上传文件：生成 id → save 字节 → INSERT 元数据。

        Args:
            content_type: router 经 ``validate_media_upload`` 注入的魔数检测 MIME
                         （**禁止** service 硬编码）。

        DB 写入失败时 best-effort 补偿 delete storage 字节。
        """
        media_id = uuid.uuid4()
        storage_key = _make_storage_key(media_id)

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
            # 注意：不使用 asset.created_at——flush 后该 server_default 属性未加载，
            # async 下访问会触发 MissingGreenlet（见 media-storage 遗留备注）。
            created_at=datetime.now(UTC),
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

    async def get_detail(
        self,
        media_id: str,
        user_id: str | None = None,
    ) -> MediaDetail:
        """查询媒体元数据 JSON（非二进制）。

        - 不存在 → 404
        - ``owner_only`` 且非 owner → 403（读权限与 ``GET /media/{id}/file`` 一致）
        """
        asset = await self._load(uuid.UUID(media_id), fresh=True)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        if asset.visibility != "public" and str(asset.owner_user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问该媒体",
            )
        return MediaDetail(
            id=str(asset.id),
            url=f"/media/{asset.id}/file",
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            visibility=asset.visibility,
            original_filename=asset.original_filename,
            created_at=asset.created_at,
        )

    async def assert_owned_by(self, media_id: str, user_id: str) -> None:
        """断言 media 存在且属于当前用户。

        - 不存在 → 404
        - 非 owner → 403（直接比较 ``owner_user_id == user_id``，
          **禁止**用 can_read 判定所有权——public 会让任意用户读权限通过）
        """
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        if str(asset.owner_user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作该媒体",
            )

    async def assert_image_content_type(self, media_id: str) -> None:
        """断言 media ``content_type`` 为 ``image/*``。

        - 不存在 → 404
        - 非 image/* → 422 + INVALID_MEDIA_TYPE（message 含 media_id 便于定位）
        """
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        if not asset.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "INVALID_MEDIA_TYPE",
                    # message 须含 media_id 字面量 + 值，便于客户端定位（spec 要求）
                    "message": f"Media media_id={media_id} content_type must be image/*",
                },
            )

    async def mark_public(self, media_id: str) -> None:
        """将 media 标记为 ``public``（attach 成功后调用）。"""
        asset = await self._load(uuid.UUID(media_id))
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        asset.visibility = "public"

    async def resolve_urls(self, media_ids: list[str]) -> dict[str, str]:
        """批量映射**存在**的 media id → ``/media/{id}/file``。

        缺失的 id 不出现于返回 dict（业务响应侧填 null）。
        """
        if not media_ids:
            return {}
        if self._repo is not None:
            assets = await self._repo.get_many_by_ids(media_ids)
            return {str(a.id): f"/media/{a.id}/file" for a in assets}
        return {
            media_id: f"/media/{media_id}/file"
            for media_id in media_ids
            if self._assets.get(uuid.UUID(media_id)) is not None
        }

    async def count_references(self, media_id: str) -> int:
        """统计 media 被业务表 FK 引用的数量（users/shops/products）。

        单元模式（无 DB repository）恒返回 0。
        """
        if self._repo is None:
            return 0
        return await self._repo.count_references(uuid.UUID(media_id))

    # ── 内部：双路径（DB repository 或进程内 dict）───────────────────────

    async def _persist(self, asset: MediaAsset) -> None:
        """INSERT media_assets。"""
        if self._repo is not None:
            await self._repo.insert(asset)
        else:
            self._assets[asset.id] = asset

    async def _load(
        self,
        media_id: uuid.UUID,
        *,
        fresh: bool = False,
    ) -> MediaAsset | None:
        """SELECT by id。

        fresh=True 时忽略 identity map 缓存，读取当前持久化状态（get_detail 用）。
        """
        if self._repo is not None:
            return await self._repo.get_by_id(media_id, fresh=fresh)
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
