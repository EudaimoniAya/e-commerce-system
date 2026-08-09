"""catalog 域内部共享的 media URL 解析 helper（product / shop service 共用）。"""

from app.media.service import MediaService


async def resolve_single_url(media_service: MediaService, media_id) -> str | None:
    """解析单个 media_id → ``/media/{id}/file``（缺失行 → None）。"""
    if media_id is None:
        return None
    media_id_str = str(media_id)
    urls = await media_service.resolve_urls([media_id_str])
    return urls.get(media_id_str)


async def resolve_urls_batch(media_service: MediaService, media_ids) -> dict[str, str]:
    """批量解析 media_id → URL（去重、忽略 None；空列表 → {}）。"""
    ids = list({str(m) for m in media_ids if m is not None})
    if not ids:
        return {}
    return await media_service.resolve_urls(ids)
