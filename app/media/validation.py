"""上传校验链：流式大小计数、MIME 白名单、魔数检测。

校验顺序（与 spec 对齐）：
1. 大小未超 ``media_max_size_bytes`` → 否则 413
2. MIME 属白名单（JPEG / PNG / WebP / PDF / TXT）→ 否则 422
3. 魔数检测 → 不匹配客户端声明则 422
4. 持久化 content_type 取魔数结果

白名单含商品文档类型（text/plain、application/pdf）——ai-rag-acl-index 将商家
上传的商品文档作为 RAG 语料（source_kind=media_document）；PDF/TXT 为 MVP 文档化边界
（OCR 图片型 PDF、Word(.docx) 不在 Change 2 范围）。
"""

from fastapi import HTTPException, status

# MIME 白名单（不含 image/svg+xml；含商品文档 text/plain / application/pdf）
_ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "text/plain",
    }
)

# 魔数字节签名 → MIME 映射
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),  # JPEG: SOI marker
    (b"\x89PNG\r\n\x1a\n", "image/png"),  # PNG: 8-byte signature
    (b"RIFF", "image/webp"),  # WebP: RIFF container（需进一步验证 WEBP）
    (b"%PDF-", "application/pdf"),  # PDF: %PDF- 版本头
]


def _is_plain_text(data: bytes) -> bool:
    """判定字节是否为可解码的 UTF-8 文本（text/plain 无固定魔数）。

    二进制（图片/PDF/乱码）通常无法完整按 UTF-8 解码 → False。
    """
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def detect_content_type(data: bytes) -> str | None:
    """通过文件头魔数检测 MIME 类型。

    返回 ``image/jpeg`` / ``image/png`` / ``image/webp`` / ``application/pdf``
    / ``text/plain``，无法识别时返回 ``None``。

    - WebP 需额外验证 RIFF 容器内含 ``WEBP`` 标识。
    - text/plain 无魔数：无已知二进制魔数且 UTF-8 可解码时判定为文本。
    """
    for magic, mime in _MAGIC_SIGNATURES:
        if data.startswith(magic):
            # WEBP 需要额外验证：RIFF 容器内须含 WEBP 标识
            if mime == "image/webp":
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return mime
                continue
            return mime
    # 文本兜底：无已知二进制魔数且 UTF-8 可解码 → text/plain
    if _is_plain_text(data):
        return "text/plain"
    return None


def validate_media_upload(
    data: bytes,
    declared_content_type: str,
    max_size_bytes: int,
) -> str:
    """按序执行上传校验链，返回魔数检测得出的 MIME 类型。

    Raises:
        HTTPException(413): 超过大小上限。
        HTTPException(422): MIME 不在白名单 / 魔数不匹配 / 无法识别。
    """
    # 1. 大小校验
    if len(data) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="文件大小超过上限",
        )

    # 2. MIME 白名单
    if declared_content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="不支持的文件类型",
        )

    # 3. 魔数检测
    detected = detect_content_type(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="无法识别的文件格式",
        )

    # 4. 魔数与声明一致性（SVG 在此被拦截）
    if detected != declared_content_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="文件内容与声明的类型不匹配",
        )

    return detected
