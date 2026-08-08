"""engagement 域 POST /favorites/batch-delete integration 测试（TDD 红阶段）。

覆盖批量删除指定 product_ids、保留未提交 id、空列表 422 与未认证 401。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.db.engagement import seed_favorite
from tests.testkit.helper.engagement import (
    batch_delete_favorites,
    list_favorites,
)
from tests.testkit.helper.ordering import arrange_purchasable_product
from tests.testkit.utils import bearer_headers, decode_jwt_sub


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_batch_delete")
@allure.title("batch-delete 删除提交的 unavailable product_ids，保留 items 侧收藏。")
async def test_batch_delete_removes_submitted_unavailable_keeps_items(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """前端从 unavailable_items 收集 product_ids 提交；仅删除列表内行，items 不受影响。"""
    _, available_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="batch-keep",
    )
    _, unpublished_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="batch-unpublished",
    )
    fake_product_id = "00000000-0000-4000-8000-000000000000"

    user_id = decode_jwt_sub(authenticated_user.access_token)
    headers = bearer_headers(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=available_product,
    )
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=unpublished_product,
    )
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=fake_product_id,
    )

    result = await batch_delete_favorites(
        integration_client,
        headers=headers,
        product_ids=[unpublished_product, fake_product_id],
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body["deleted_count"] == 2

    after = await list_favorites(
        integration_client,
        headers=headers,
    )
    assert after.status_code == 200
    assert after.body is not None
    assert after.body["total"] == 1
    assert [i["product_id"] for i in after.body["items"]] == [available_product]
    assert after.body["unavailable_items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_batch_delete")
@allure.title("batch-delete 未收藏的 product_id 跳过，deleted_count 为实际删除数。")
async def test_batch_delete_skips_not_favorited_ids(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """提交的 id 含未收藏项时仍 200；deleted_count 仅计实际删除行。"""
    _, available_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="batch-skip",
    )
    not_favorited_id = "00000000-0000-4000-8000-000000000001"

    user_id = decode_jwt_sub(authenticated_user.access_token)
    headers = bearer_headers(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=available_product,
    )

    result = await batch_delete_favorites(
        integration_client,
        headers=headers,
        product_ids=[available_product, not_favorited_id],
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body["deleted_count"] == 1

    after = await list_favorites(integration_client, headers=headers)
    assert after.status_code == 200
    assert after.body is not None
    assert after.body["total"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_batch_delete")
@allure.title("batch-delete 空 product_ids 返回 422。")
async def test_batch_delete_empty_product_ids_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """与 batch-pay 一致：空列表 422。"""
    result = await batch_delete_favorites(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_ids=[],
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_batch_delete")
@allure.title("未认证访问 batch-delete 返回 401。")
async def test_batch_delete_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 POST /favorites/batch-delete 返回 401。"""
    r = await integration_client.post(
        "/favorites/batch-delete",
        json={"product_ids": ["00000000-0000-4000-8000-000000000000"]},
    )
    assert r.status_code == 401
