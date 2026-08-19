"""上传校验链单元测试：魔数检测 + MIME 白名单 + 大小校验（TDD 红阶段）。"""

import allure
import pytest

from app.media.validation import (
    detect_content_type,
    validate_media_upload,
)
from tests.testkit.helper.media import (
    MINI_JPEG_BYTES,
    MINI_PNG_BYTES,
    MINI_WEBP_BYTES,
    SVG_BYTES,
    TEXT_BYTES,
)

# ── detect_content_type（魔数 → MIME）─────────────────────────────────────────


@pytest.mark.parametrize(
    "data,expected_mime",
    [
        pytest.param(b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg", id="jpeg_soi"),
        pytest.param(b"\xff\xd8\xff", "image/jpeg", id="jpeg_minimal"),
        pytest.param(b"\x89PNG\r\n\x1a\n", "image/png", id="png"),
        pytest.param(MINI_JPEG_BYTES, "image/jpeg", id="full_jpeg"),
        pytest.param(MINI_PNG_BYTES, "image/png", id="full_png"),
        pytest.param(MINI_WEBP_BYTES, "image/webp", id="full_webp"),
        # TXT 商品文档：无固定魔数，UTF-8 可解码即判 text/plain（design D4）
        pytest.param(TEXT_BYTES, "text/plain", id="plain_text"),
    ],
)
@allure.epic("media")
@allure.feature("validation")
@allure.title("detect_content_type 识别合法类型返回正确 MIME")
def test_detect_content_type_valid(data: bytes, expected_mime: str) -> None:
    """合法魔数 / 可解码文本应被检测为正确的 MIME 类型。"""
    assert detect_content_type(data) == expected_mime


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(SVG_BYTES, id="svg_xml"),
        pytest.param(b"", id="empty"),
        pytest.param(b"\x00\x00\x00\x00", id="null_bytes"),
        pytest.param(b"GIF89a\x00\x00\x00", id="gif_unsupported"),
    ],
)
@allure.epic("media")
@allure.feature("validation")
@allure.title("detect_content_type 对不支持格式返回 None")
def test_detect_content_type_invalid(data: bytes) -> None:
    """空字节 / 纯控制字符 / 已知但不支持的二进制与标记格式（GIF、SVG-XML）应返回 None。"""
    assert detect_content_type(data) is None


# ── validate_media_upload ─────────────────────────────────────────────────────


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload PNG 通过校验")
def test_validate_png_passes() -> None:
    """合法 PNG 且大小未超限应通过校验。"""
    validate_media_upload(
        data=MINI_PNG_BYTES,
        declared_content_type="image/png",
        max_size_bytes=5 * 1024 * 1024,
    )


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload JPEG 通过校验")
def test_validate_jpeg_passes() -> None:
    """合法 JPEG 且大小未超限应通过校验。"""
    validate_media_upload(
        data=MINI_JPEG_BYTES,
        declared_content_type="image/jpeg",
        max_size_bytes=5 * 1024 * 1024,
    )


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload WebP 通过校验")
def test_validate_webp_passes() -> None:
    """合法 WebP 且大小未超限应通过校验。"""
    validate_media_upload(
        data=MINI_WEBP_BYTES,
        declared_content_type="image/webp",
        max_size_bytes=5 * 1024 * 1024,
    )


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload SVG 被拒绝（422）")
def test_validate_svg_rejected() -> None:
    """SVG 文件应被拒绝，抛出 422。"""
    with pytest.raises(Exception) as exc_info:
        validate_media_upload(
            data=SVG_BYTES,
            declared_content_type="image/svg+xml",
            max_size_bytes=5 * 1024 * 1024,
        )
    # 预期为 HTTPException(422) 或自定义 InvalidMediaError
    assert "422" in str(exc_info.value) or "422" in str(
        getattr(exc_info.value, "status_code", "")
    )


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload 超过大小上限被拒绝")
def test_validate_oversized_rejected() -> None:
    """超过 max_size_bytes 的数据应被拒绝（413）。"""
    # 构造超限数据：合法 PNG 头 + 填充，max_size=10 bytes
    data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    with pytest.raises(Exception) as exc_info:
        validate_media_upload(
            data=data,
            declared_content_type="image/png",
            max_size_bytes=10,
        )
    assert "413" in str(exc_info.value) or "413" in str(
        getattr(exc_info.value, "status_code", "")
    )


@allure.epic("media")
@allure.feature("validation")
@allure.title("validate_media_upload 魔数与声明的 Content-Type 不匹配被拒绝")
def test_validate_magic_mismatch_rejected() -> None:
    """魔数检测结果与客户端声明不一致时应被拒绝（422）。"""
    # JPEG 魔数但声称 PNG
    with pytest.raises(Exception) as exc_info:
        validate_media_upload(
            data=MINI_JPEG_BYTES,
            declared_content_type="image/png",
            max_size_bytes=5 * 1024 * 1024,
        )
    assert "422" in str(exc_info.value) or "422" in str(
        getattr(exc_info.value, "status_code", "")
    )
