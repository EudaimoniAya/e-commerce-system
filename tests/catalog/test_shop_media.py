"""catalog 域 shop logo attach integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/catalog-shop/spec.md MODIFIED Requirements）：
- POST /shops 带 logo_media_id → 201 + logo_url resolve
- PATCH /shops/me 更新 logo_media_id → 200 + logo_url resolve
- 绑他人 media → 403
- 非 image attach → 422
- 清空 logo → logo_url=null

.. note::
    本文件 **仅编写测试**，不编写 catalog/media attach 实现。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.builders import build_shop_create
from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.auth import auth_headers, register_user_via_otp
from tests.testkit.helper.media import (
    MINI_PNG_BYTES,
    insert_non_image_media,
    upload_media,
)
from tests.testkit.utils import bearer_headers


async def _upload_png(client: AsyncClient, token: str) -> str:
    result = await upload_media(
        client,
        headers=auth_headers(token),
        file_bytes=MINI_PNG_BYTES,
        filename="logo.png",
        content_type="image/png",
    )
    assert result.status_code == 201
    assert result.body is not None
    return result.body["id"]


# ── POST /shops attach 成功 ────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("shop_media")
@allure.title("POST /shops 带 logo_media_id 返回 201 且 logo_url resolve")
async def test_create_shop_with_logo_media_id(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """POST /shops 带合法 logo_media_id → 201 + logo_url。"""
    media_id = await _upload_png(integration_client, authenticated_user.access_token)

    shop_request = build_shop_create(logo_media_id=media_id)
    response = await integration_client.post(
        "/shops",
        json=shop_request.model_dump(mode="json"),
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["logo_url"] == f"/media/{media_id}/file"


# ── PATCH /shops/me attach 成功 ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("shop_media")
@allure.title("PATCH /shops/me 更新 logo_media_id 返回 200 且 logo_url resolve")
async def test_update_shop_logo_media_id(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """PATCH /shops/me 更新 logo_media_id → 200 + logo_url。"""
    media_id = await _upload_png(integration_client, shop_owner.access_token)

    response = await integration_client.patch(
        "/shops/me",
        json={"logo_media_id": media_id},
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 200
    assert response.json()["logo_url"] == f"/media/{media_id}/file"


# ── 403：绑他人 media ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("shop_media")
@allure.title("PATCH 他人 media 返回 403")
async def test_attach_others_logo_media_returns_403(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """PATCH 非本人 owner 的 logo_media_id → 403。"""
    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None
    others_media_id = await _upload_png(
        integration_client, other_user.body.access_token
    )

    response = await integration_client.patch(
        "/shops/me",
        json={"logo_media_id": others_media_id},
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 403


# ── 422：非 image attach ────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("shop_media")
@allure.title("非 image media attach 返回 422")
async def test_attach_non_image_logo_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    db_session: AsyncSession,
) -> None:
    """PATCH 非 image 类型 media → 422。"""
    text_media_id = await insert_non_image_media(db_session, shop_owner.access_token)

    response = await integration_client.patch(
        "/shops/me",
        json={"logo_media_id": text_media_id},
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 422


# ── 清空 logo ───────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("shop_media")
@allure.title("清空 logo_media_id 后 logo_url 为 null")
async def test_clear_logo_media_id(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """PATCH logo_media_id=null → 200 + logo_url=null。"""
    # 先设置 logo
    media_id = await _upload_png(integration_client, shop_owner.access_token)
    set_resp = await integration_client.patch(
        "/shops/me",
        json={"logo_media_id": media_id},
        headers=bearer_headers(shop_owner.access_token),
    )
    assert set_resp.status_code == 200

    # 清空
    clear_resp = await integration_client.patch(
        "/shops/me",
        json={"logo_media_id": None},
        headers=bearer_headers(shop_owner.access_token),
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["logo_url"] is None
