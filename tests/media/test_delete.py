"""media 域删除集成测试：DELETE /media/{id}（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


async def _upload_for_owner(client: AsyncClient, token: str) -> str:
    """上传文件并返回 media id。"""
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
@allure.feature("delete")
@allure.title("owner 删除自己的 media 返回 204")
async def test_delete_owner_returns_204(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """拥有者删除自己的 media 应返回 204。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(authenticated_user.access_token),
    )

    assert response.status_code == 204


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete")
@allure.title("删除后 GET 同一 media 返回 404")
async def test_delete_then_download_returns_404(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """删除后再次下载同一文件应返回 404。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    # 删除
    del_response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(authenticated_user.access_token),
    )
    assert del_response.status_code == 204

    # 确认已消失
    get_response = await integration_client.get(
        f"/media/{media_id}/file",
        headers=auth_headers(authenticated_user.access_token),
    )
    assert get_response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete")
@allure.title("非 owner 删除返回 403")
async def test_delete_non_owner_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """非拥有者尝试删除应返回 403。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(other_user.body.access_token),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete")
@allure.title("匿名删除返回 401")
async def test_delete_unauthenticated_returns_401(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """未认证用户删除应返回 401。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.delete(f"/media/{media_id}")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete")
@allure.title("非 owner 删除 public media 返回 403")
async def test_delete_public_media_non_owner_returns_403(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
    db_session: AsyncSession,
) -> None:
    """非 owner 已认证用户 DELETE public media → 403（bugfix: 禁止用 can_read 做所有权校验）。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )
    # 模拟 mark_public（该功能尚未实现，用 DB 操作模拟）
    await db_session.execute(
        text("UPDATE media_assets SET visibility='public' WHERE id=:id"),
        {"id": media_id},
    )
    await db_session.commit()

    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(other_user.body.access_token),
    )

    assert response.status_code == 403
