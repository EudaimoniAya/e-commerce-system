"""ai 域 media 文档解析：PDF（pymupdf）/ TXT → 文本。

边界（design D4）：OCR 图片型 PDF、Word(.docx) **不做**（MVP 文档化边界）。
解析失败记日志并返回空串（不抛错——reindex 跳过该 document，不阻塞整店）。
"""

import fitz  # pymupdf（包模块名为 fitz）
from loguru import logger


def parse_document(content_type: str, data: bytes) -> str:
    """按 content_type 解析 PDF/TXT → 文本；失败返回空串不抛错。

    Returns:
        提取文本（空页/空文件返回空串）。
    """
    try:
        if content_type == "text/plain":
            return _parse_txt(data)
        if content_type == "application/pdf":
            return _parse_pdf(data)
        # 其它 content_type（图片等）不解析——本 change 仅商品文档 PDF/TXT
        return ""
    except Exception:
        logger.warning("文档解析失败，跳过该 document（content_type={})", content_type)
        return ""


def _parse_txt(data: bytes) -> str:
    """TXT：UTF-8 解码。"""
    return data.decode("utf-8")


def _parse_pdf(data: bytes) -> str:
    """PDF：pymupdf 提取全部页文本（空页返回空串）。"""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
