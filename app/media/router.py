"""media 域 HTTP 路由：POST /media、GET /media/{id}/file、DELETE /media/{id}。

- POST /media：multipart/form-data，JWT 必选 → 201 MediaSummary
- GET /media/{id}/file：JWT 可选 → 二进制流，``X-Content-Type-Options: nosniff``
- DELETE /media/{id}：JWT 必选，仅 owner → 204
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.responses import Response as StarletteResponse

from app.infra.auth import decode_access_token
from app.infra.config import Settings, get_settings
from app.media.deps import get_media_service
from app.media.rate_limit import check_upload_rate_limit
from app.media.schemas import MediaSummary
from app.media.service import MediaService
from app.media.validation import validate_media_upload

from fastapi.security import OAuth2PasswordBearer

router = APIRouter(prefix="/media", tags=["media"])

# 必选鉴权（无 token → 401）
_required_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
# 可选鉴权（无 token → None，不抛 401）
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ── 鉴权依赖 ──────────────────────────────────────────────────────────────


async def _required_user_id(
    token: str = Depends(_required_oauth2),
) -> uuid.UUID:
    """Bearer JWT 必选 → 返回 user_id（否则 401）。"""
    return decode_access_token(token)


async def _optional_user_id(
    token: str | None = Depends(_optional_oauth2),
) -> uuid.UUID | None:
    """Bearer JWT 可选 → 返回 user_id 或 None。"""
    if token is None:
        return None
    try:
        return decode_access_token(token)
    except HTTPException:
        return None


# ── 端点 ─────────────────────────────────────────────────────────────────


@router.post("", response_model=MediaSummary, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile,
    user_id: uuid.UUID = Depends(_required_user_id),
    _rate_ok: None = Depends(check_upload_rate_limit),
    service: MediaService = Depends(get_media_service),
    settings: Settings = Depends(get_settings),
) -> MediaSummary:
    """上传媒体文件（multipart/form-data，字段 ``file``）。

    校验链：大小上限 → MIME 白名单 → 魔数检测。
    返回 201 与 ``MediaSummary``（含相对 URL ``/media/{id}/file``）。
    """
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="缺少文件名",
        )

    # 大小预检：Starlette 解析期已累加 file.size，read 前即可拦截超大文件
    # （避免 read() 全量读入内存后才 413——那已经爆内存了）
    if file.size is not None and file.size > settings.media_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="文件大小超过上限",
        )

    # 全量读入内存（预检已拦截超大文件，5MB 上限下安全）
    raw = await file.read()

    # 校验链（大小 → MIME 白名单 → 魔数检测 → 声明一致性）
    _content_type = validate_media_upload(
        data=raw,
        declared_content_type=file.content_type or "application/octet-stream",
        max_size_bytes=settings.media_max_size_bytes,
    )

    return await service.upload(
        file_bytes=raw,
        original_filename=file.filename,
        owner_user_id=str(user_id),
    )


@router.get("/{media_id}/file")
async def download_media(
    media_id: str,
    user_id: uuid.UUID | None = Depends(_optional_user_id),
    service: MediaService = Depends(get_media_service),
) -> StreamingResponse:
    """下载媒体文件二进制流。

    - ``public`` 文件：无需鉴权
    - ``owner_only`` 文件：非 owner 返回 403
    - 响应头含 ``X-Content-Type-Options: nosniff``
    """
    # 读权限校验（403 / 404）
    user_id_str = str(user_id) if user_id is not None else None
    can_read = await service.can_read(media_id=media_id, user_id=user_id_str)
    if not can_read:
        # 区分 404 与 403：先查 asset 是否存在
        try:
            _, _ = await service.get_file_stream(media_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该文件",
        )

    try:
        data, content_type = await service.get_file_stream(media_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="媒体文件不存在",
        )

    return StreamingResponse(
        content=iter([data]),
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{media_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: str,
    user_id: uuid.UUID = Depends(_required_user_id),
    service: MediaService = Depends(get_media_service),
) -> StarletteResponse:
    """删除媒体资产。

    仅 ``owner_user_id`` 匹配者可删（非 owner → 403）。
    不检查业务表 FK 引用（留给 ``media-wire`` change）。
    """
    # 所有权校验
    can_read = await service.can_read(media_id=media_id, user_id=str(user_id))
    if not can_read:
        # 区分 403 vs 404
        try:
            _, _ = await service.get_file_stream(media_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="媒体文件不存在",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除该文件",
        )

    try:
        await service.delete(media_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="媒体文件不存在",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
