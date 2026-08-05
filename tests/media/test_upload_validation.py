"""media 域上传校验集成测试：超大 / SVG / 魔数不匹配（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers
from tests.support.helper.media import MINI_PNG_BYTES, SVG_BYTES, TEXT_BYTES, upload_media


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload_validation")
@allure.title("上传超过大小上限的文件返回 413 或 422")
async def test_upload_oversized_returns_413_or_422(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """超过 media_max_size_bytes 的上传应被拒绝。"""
    # 10 MB 数据（默认上限 5 MB）
    large_data = b"x" * (10 * 1024 * 1024)
    result = await upload_media(
        integration_client,
        headers=auth_headers(authenticated_user.access_token),
        file_bytes=large_data,
        filename="large.bin",
        content_type="image/png",
    )

    assert result.status_code in (413, 422)


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload_validation")
@allure.title("上传 SVG 文件返回 422")
async def test_upload_svg_returns_422(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """上传 SVG 文件应被拒绝，返回 422。"""
    result = await upload_media(
        integration_client,
        headers=auth_headers(authenticated_user.access_token),
        file_bytes=SVG_BYTES,
        filename="image.svg",
        content_type="image/svg+xml",
    )

    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload_validation")
@allure.title("上传魔数不匹配文件返回 422")
async def test_upload_magic_mismatch_returns_422(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """魔数与声明 Content-Type 不匹配的上传应被拒绝。"""
    result = await upload_media(
        integration_client,
        headers=auth_headers(authenticated_user.access_token),
        file_bytes=TEXT_BYTES,
        filename="fake.png",
        content_type="image/png",
    )

    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload_validation")
@allure.title("持久化的 content_type 应为魔数检测结果而非客户端声明")
async def test_upload_persists_detected_content_type(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """持久化的 content_type 应来自魔数检测，而非客户端声明的 Content-Type。"""
    result = await upload_media(
        integration_client,
        headers=auth_headers(authenticated_user.access_token),
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
        content_type="image/png",
    )

    assert result.status_code == 201
    assert result.body is not None
    assert result.body["content_type"] == "image/png"
