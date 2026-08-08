"""media 域 GET /media/{id} JSON 元数据集成测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/media-storage/spec.md ADDED Requirement "Get media metadata by id"）：
- public media 匿名 GET → 200 + 完整元数据字段
- owner_only 非 owner → 403
- owner 读 owner_only → 200
- 不存在 → 404
- 响应不暴露 storage_key / owner_user_id

.. note::
    本文件 **仅编写测试**，不编写 GET /media/{id} 路由与 get_detail 实现。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


async def _upload_for_owner(client: AsyncClient, token: str) -> str:
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


# ── 200：public media 匿名可读 ─────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("metadata")
@allure.title("public media 匿名 GET /media/{id} 返回 200 + 完整元数据")
async def test_public_media_metadata_anonymous(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
    db_session: AsyncSession,
) -> None:
    """visibility=public 的 media，匿名 GET 元数据应返回 200 + 不含敏感字段。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )
    # 直接设 public（mark_public 尚未实现，用 DB 操作模拟）
    await db_session.execute(
        text("UPDATE media_assets SET visibility='public' WHERE id=:id"),
        {"id": media_id},
    )
    await db_session.commit()

    response = await integration_client.get(f"/media/{media_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == media_id
    assert body["url"] == f"/media/{media_id}/file"
    assert "content_type" in body
    assert "size_bytes" in body
    assert body["visibility"] == "public"
    assert "created_at" in body
    # 不得暴露内部字段
    assert "storage_key" not in body
    assert "owner_user_id" not in body


# ── 403：owner_only 非 owner 不可读 ─────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("metadata")
@allure.title("owner_only media 匿名 GET 返回 403")
async def test_owner_only_media_metadata_anonymous_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """visibility=owner_only 的 media，匿名 GET 元数据返回 403。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.get(f"/media/{media_id}")

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("metadata")
@allure.title("owner_only media 非 owner 已认证 GET 返回 403")
async def test_owner_only_media_metadata_non_owner_returns_403(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """非 owner 已认证用户 GET owner_only 元数据 → 403。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None

    response = await integration_client.get(
        f"/media/{media_id}",
        headers=auth_headers(other_user.body.access_token),
    )

    assert response.status_code == 403


# ── 200：owner 读 owner_only ────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("metadata")
@allure.title("owner GET owner_only media 返回 200 + 完整元数据")
async def test_owner_reads_owner_only_metadata_returns_200(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """owner GET 自己的 owner_only media 元数据 → 200。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )

    response = await integration_client.get(
        f"/media/{media_id}",
        headers=auth_headers(authenticated_user.access_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == media_id


# ── 404：不存在 ─────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("metadata")
@allure.title("不存在 media 的 GET /media/{id} 返回 404")
async def test_missing_media_metadata_returns_404(
    integration_client: AsyncClient,
) -> None:
    """GET 不存在的 media id → 404。"""
    response = await integration_client.get(
        "/media/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
