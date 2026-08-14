"""media 域 HTTP helper 与 fixture bytes。"""

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.results import MediaResult
from tests.testkit.utils import decode_jwt_sub

# ── Fixture bytes ────────────────────────────────────────────────────────────

# 最小合法 1x1 PNG（67 字节）
MINI_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"  # PNG 文件头签名
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

# 最小合法 JPEG（灰色 1x1，约 107 字节）
MINI_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f"
    b"\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00"
    b"\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\n\x0b\xff\xda"
    b"\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9"
)

# 最小合法 WebP（RIFF 容器含 VP8L 编码数据）
MINI_WEBP_BYTES = (
    b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0a\x00\x00\x00"
    b"\x2f\x00\x00\x00\x00\x01\x00\x01\x00\x00\xff\x00\xff\x00\xff"
)

# SVG 字节（用于拒绝测试）
SVG_BYTES = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'

# 纯文本字节（用于魔数不匹配测试）
TEXT_BYTES = b"this is plain text, not an image"


# ── HTTP helper ──────────────────────────────────────────────────────────────


async def upload_media(
    client: AsyncClient,
    *,
    headers: dict[str, str] | None = None,
    file_bytes: bytes | None = None,
    filename: str = "test.png",
    content_type: str = "image/png",
) -> MediaResult:
    """调用 POST /media（multipart/form-data），返回 MediaResult。

    Args:
        client: httpx AsyncClient。
        headers: 额外请求头（需含 Authorization Bearer）。
        file_bytes: 上传字节；None 时使用 MINI_PNG_BYTES。
        filename: multipart 文件名。
        content_type: 声明的 Content-Type。
    """
    data = file_bytes if file_bytes is not None else MINI_PNG_BYTES
    files = {"file": (filename, data, content_type)}
    response = await client.post("/media", files=files, headers=headers or {})
    body = None
    if response.content:
        try:
            body = response.json()
        except Exception:
            body = None
    return MediaResult(status_code=response.status_code, body=body)


async def insert_non_image_media(db_session: AsyncSession, token: str) -> str:
    """直接插入一条 ``content_type=text/plain`` 的 media 行（非 image）并返回 media_id。

    media-storage upload 校验仅收 ``image/*``，非 image media 无法经 ``POST /media``
    创建；attach 的 422 场景需绕过 HTTP、直接写库模拟一条非 image 记录（owner 为
    ``token`` 对应用户）。
    """
    user_id = decode_jwt_sub(token)
    media_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO media_assets "
            "(id, owner_user_id, visibility, content_type, size_bytes, storage_key, original_filename) "
            "VALUES (:id, :owner, 'owner_only', 'text/plain', 4, :key, 'doc.txt')"
        ),
        {
            "id": media_id,
            "owner": user_id,
            "key": f"{media_id[:2]}/{media_id[2:4]}/{media_id}",
        },
    )
    await db_session.commit()
    return media_id
