"""media 域上传集成测试：POST /media（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload")
@allure.title("已认证用户上传合法 PNG 返回 201 与 MediaSummary 形状")
async def test_upload_png_returns_201(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """已认证用户上传合法 PNG 应返回 201 且响应体符合 MediaSummary 形状。"""
    result = await upload_media(
        integration_client,
        headers=auth_headers(authenticated_user.access_token),
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
        content_type="image/png",
    )

    assert result.status_code == 201
    body = result.body
    assert body is not None
    assert "id" in body
    assert "url" in body
    assert body["url"] == f"/media/{body['id']}/file"
    assert "content_type" in body
    assert body["content_type"] == "image/png"
    assert "size_bytes" in body
    assert body["size_bytes"] == len(MINI_PNG_BYTES)
    assert "created_at" in body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload")
@allure.title("已认证用户上传合法 JPEG 返回 201")
async def test_upload_jpeg_returns_201(
    integration_client: AsyncClient,
) -> None:
    """已认证用户上传合法 JPEG 应返回 201。"""
    user = await register_user_via_otp(integration_client)
    assert user.status_code == 201 and user.body is not None

    result = await upload_media(
        integration_client,
        headers=auth_headers(user.body.access_token),
        file_bytes=MINI_PNG_BYTES,  # 绿阶段替换为 MINI_JPEG_BYTES
        filename="photo.jpg",
        content_type="image/jpeg",
    )

    assert result.status_code == 201
    assert result.body is not None
    assert "id" in result.body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("upload")
@allure.title("未认证用户上传返回 401")
async def test_upload_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未携带 Bearer token 上传应返回 401。"""
    result = await upload_media(
        integration_client,
        headers=None,  # 不传 Authorization
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
    )

    assert result.status_code == 401
