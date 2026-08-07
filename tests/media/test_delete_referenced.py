"""media 域 DELETE 409 被引用集成测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/media-storage/spec.md MODIFIED Requirement "Delete media by owner"）：
- avatar 引用 → DELETE 409
- logo 引用 → DELETE 409
- product 主图引用 → DELETE 409
- 无引用 → DELETE 204（已有测例覆盖）

.. note::
    本文件 **仅编写测试**，不编写 count_references 与 DELETE 409 实现。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.helper.auth import auth_headers
from tests.support.helper.catalog import create_category
from tests.support.helper.media import MINI_PNG_BYTES, upload_media
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.utils import bearer_headers


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


# ── avatar 引用 → 409 ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete_referenced")
@allure.title("avatar_media_id 引用 → DELETE 409")
async def test_delete_media_referenced_by_avatar_returns_409(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
    db_session: AsyncSession,
) -> None:
    """media 被 users.avatar_media_id 引用时 DELETE → 409。"""
    media_id = await _upload_for_owner(
        integration_client, authenticated_user.access_token
    )
    # 模拟 attach：直接写 FK（avatar_media_id 实现尚未就绪）
    await db_session.execute(
        text("UPDATE users SET avatar_media_id=:mid WHERE id=:uid"),
        {"mid": media_id, "uid": "does-not-exist-placeholder"},
    )
    # 使用当前用户的 id
    from tests.support.utils import decode_jwt_sub
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await db_session.execute(
        text("UPDATE users SET avatar_media_id=:mid WHERE id=:uid"),
        {"mid": media_id, "uid": user_id},
    )
    await db_session.commit()

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(authenticated_user.access_token),
    )

    assert response.status_code == 409


# ── logo 引用 → 409 ───────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete_referenced")
@allure.title("logo_media_id 引用 → DELETE 409")
async def test_delete_media_referenced_by_logo_returns_409(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    db_session: AsyncSession,
) -> None:
    """media 被 shops.logo_media_id 引用时 DELETE → 409。"""
    media_id = await _upload_for_owner(
        integration_client, shop_owner.access_token
    )
    # 模拟 attach：直接写 FK
    await db_session.execute(
        text("UPDATE shops SET logo_media_id=:mid WHERE id=:sid"),
        {"mid": media_id, "sid": shop_owner.shop_id},
    )
    await db_session.commit()

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(shop_owner.access_token),
    )

    assert response.status_code == 409


# ── product 主图引用 → 409 ────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("delete_referenced")
@allure.title("primary_media_id 引用 → DELETE 409")
async def test_delete_media_referenced_by_product_returns_409(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    db_session: AsyncSession,
) -> None:
    """media 被 products.primary_media_id 引用时 DELETE → 409。"""
    media_id = await _upload_for_owner(
        integration_client, shop_owner.access_token
    )
    # 创建商品并模拟 attach：先 seed 一个类目（products 无 category 行不可存在）
    category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
    )
    assert category.status_code == 201 and category.body is not None
    cid = category.body.id
    import uuid as _uuid
    pid = str(_uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO products (id, shop_id, name, price, stock, primary_media_id, is_published) "
            "VALUES (:pid, :sid, 'test', 9.99, 1, :mid, 0)"
        ),
        {"pid": pid, "sid": shop_owner.shop_id, "mid": media_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO product_categories (product_id, category_id, is_primary) "
            "VALUES (:pid, :cid, 1)"
        ),
        {"pid": pid, "cid": cid},
    )
    await db_session.commit()

    response = await integration_client.delete(
        f"/media/{media_id}",
        headers=auth_headers(shop_owner.access_token),
    )

    assert response.status_code == 409
