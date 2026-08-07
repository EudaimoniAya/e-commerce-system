"""user 域 avatar attach integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/user-auth/spec.md MODIFIED/ADDED Requirements）：
- attach 头像成功 200 + avatar_url
- 绑他人 media → 403
- 非 image attach → 422 + media_id
- 清空 avatar_media_id → 200 + avatar_url=null
- 公开 GET avatar media file
- GET /users/me 含 avatar_url

.. note::
    本文件 **仅编写测试**，不编写 user/media attach 实现。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.media import (
    MINI_PNG_BYTES,
    insert_non_image_media,
    upload_media,
)
from tests.support.contexts import AuthContext
from tests.support.utils import bearer_headers


# ── helpers ──────────────────────────────────────────────────────────────────


async def _upload_png(client: AsyncClient, token: str) -> str:
    """上传 PNG 并返回 media_id。"""
    result = await upload_media(
        client,
        headers=auth_headers(token),
        file_bytes=MINI_PNG_BYTES,
        filename="avatar.png",
        content_type="image/png",
    )
    assert result.status_code == 201
    assert result.body is not None
    return result.body["id"]


# ── attach 成功 ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("attach 本人上传的 image media 返回 200 且 avatar_url 正确")
async def test_attach_avatar_success_returns_200(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """PATCH avatar_media_id 为本人上传的 image → 200 + avatar_url。"""
    media_id = await _upload_png(integration_client, authenticated_user.access_token)

    response = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["avatar_url"] == f"/media/{media_id}/file"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("attach 后 GET /media/{id}/file 公开可访问")
async def test_avatar_media_public_after_attach(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """attach 后 media 应 mark_public，匿名可 GET /media/{id}/file。"""
    media_id = await _upload_png(integration_client, authenticated_user.access_token)

    # attach
    patch_resp = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert patch_resp.status_code == 200

    # 匿名可下载
    get_resp = await integration_client.get(f"/media/{media_id}/file")
    assert get_resp.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("GET /users/me 响应含 avatar_url")
async def test_get_me_includes_avatar_url(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """attach 后 GET /users/me 的 avatar_url 已 resolve。"""
    media_id = await _upload_png(integration_client, authenticated_user.access_token)

    patch_resp = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert patch_resp.status_code == 200

    get_resp = await integration_client.get(
        "/users/me",
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["avatar_url"] == f"/media/{media_id}/file"


# ── 403：绑他人 media ───────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("绑他人上传的 media 返回 403")
async def test_attach_others_media_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """PATCH 非本人 owner 的 avatar_media_id → 403。"""
    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None
    others_media_id = await _upload_png(
        integration_client, other_user.body.access_token
    )

    response = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": others_media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 403


# ── 422：非 image attach ────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("非 image/* media attach 返回 422 且含 media_id")
async def test_attach_non_image_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
    db_session: AsyncSession,
) -> None:
    """PATCH 非 image 类型的 media → 422 + media_id。"""
    text_media_id = await insert_non_image_media(
        db_session, authenticated_user.access_token
    )

    response = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": text_media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 422
    body = response.json()
    # 422 响应应包含 media_id 以告知哪个 media 不合法
    assert "media_id" in str(body).lower() or "media_id" in body


# ── 清空 avatar ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("avatar_media_id 为 null 清空头像")
async def test_clear_avatar_with_null(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """PATCH avatar_media_id=null → 200 + avatar_url=null。"""
    # 先设置头像
    media_id = await _upload_png(integration_client, authenticated_user.access_token)
    patch_resp = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": media_id},
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert patch_resp.status_code == 200

    # 清空头像
    clear_resp = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": None},
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["avatar_url"] is None


# ── 401：未认证 ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("user")
@allure.feature("avatar_attach")
@allure.title("未认证 PATCH /users/me 返回 401")
async def test_attach_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证 PATCH /users/me → 401。"""
    response = await integration_client.patch(
        "/users/me",
        json={"avatar_media_id": "does-not-matter"},
    )
    assert response.status_code == 401
