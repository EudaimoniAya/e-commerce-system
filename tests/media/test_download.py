"""media 域下载集成测试：GET /media/{id}/file（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


async def _upload_for_owner(
    client: AsyncClient, token: str, visibility: str = "owner_only"
) -> str:
    """上传文件并返回 media id。当前版本 visibility 固定为 owner_only。"""
    result = await upload_media(
        client,
        headers=auth_headers(token),
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
        content_type="image/png",
    )
    assert result.status_code == 201
    assert result.body is not None
    return result.body["id"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("download")
@allure.title("owner_only 文件：owner 下载返回 200 与原始字节")
async def test_download_owner_only_owner_returns_200(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """owner_only 文件的拥有者下载应返回 200 和原始字节。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.get(
        f"/media/{media_id}/file",
        headers=auth_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    assert response.content == MINI_PNG_BYTES
    assert response.headers.get("content-type") == "image/png"
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("download")
@allure.title("owner_only 文件：非 owner 下载返回 403")
async def test_download_owner_only_non_owner_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """owner_only 文件的非拥有者下载应返回 403。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None

    response = await integration_client.get(
        f"/media/{media_id}/file",
        headers=auth_headers(other_user.body.access_token),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("download")
@allure.title("owner_only 文件：匿名下载返回 403")
async def test_download_owner_only_anonymous_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """owner_only 文件的匿名下载应返回 403。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.get(f"/media/{media_id}/file")

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("download")
@allure.title("不存在的 media id 返回 404")
async def test_download_nonexistent_returns_404(
    integration_client: AsyncClient,
) -> None:
    """请求不存在的 media id 应返回 404。"""
    response = await integration_client.get(
        "/media/00000000-0000-0000-0000-000000000000/file"
    )

    assert response.status_code == 404
