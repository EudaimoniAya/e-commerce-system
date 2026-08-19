"""ai 域 media 文档解析单元测试（TDD 红阶段：app.ai.rag.parsing 未实现）。

覆盖 spec ai-rag-indexing「Media document parsing」：
- TXT 内容原样提取
- PDF 解析返回文本（空页返回空串不抛错）
- 解析失败记录日志并跳过该 document（返回空串不抛错，不阻塞 reindex）
"""

import allure

# mock 文件字节（红阶段不依赖真实 pymupdf；绿阶段实现用 pymupdf 解析）
MINI_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF"
)
TXT_BYTES = b"hello rag\nline2"
INVALID_PDF_BYTES = b"this is definitely not a pdf"


def _parse(content_type: str, data: bytes) -> str:
    """调用 parse_document（lazy import 保持红阶段 collection 成功）。"""
    from app.ai.rag.parsing import parse_document

    return parse_document(content_type=content_type, data=data)


@allure.epic("ai")
@allure.feature("parsing")
@allure.title("TXT 内容原样提取为文本")
def test_parse_txt_returns_plain_text() -> None:
    """TXT：按 UTF-8 解码返回原样文本。"""
    text = _parse(content_type="text/plain", data=TXT_BYTES)
    assert text == "hello rag\nline2"


@allure.epic("ai")
@allure.feature("parsing")
@allure.title("PDF 解析返回文本字符串（空页返回空串不抛错）")
def test_parse_pdf_returns_text() -> None:
    """PDF：解析成功返回 str；mock 空页 PDF 允许返回空串但不抛错（spec 场景）。"""
    text = _parse(content_type="application/pdf", data=MINI_PDF_BYTES)
    assert isinstance(text, str)


@allure.epic("ai")
@allure.feature("parsing")
@allure.title("解析失败返回空串不抛错（跳过该 document）")
def test_parse_invalid_pdf_returns_empty_without_raise() -> None:
    """PDF 解析失败：返回空串而不抛错（reindex 跳过该 document 并记日志）。"""
    text = _parse(content_type="application/pdf", data=INVALID_PDF_BYTES)
    assert text == ""
