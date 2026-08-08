"""engagement 域 DELETE /browse/{product_id} integration 测试（TDD 红阶段）。

覆盖删除已有浏览记录（204 + DB 行删除）、删除无记录（404）、未认证 401。
"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.db.engagement import get_browse_history, seed_browse_history
from tests.testkit.helper.engagement import delete_browse
from tests.testkit.helper.ordering import arrange_purchasable_product
from tests.testkit.utils import bearer_headers, decode_jwt_sub

# ── DELETE /browse/{product_id} ───────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_delete")
@allure.title("认证用户删除已有浏览记录成功，返回 204 并删除行。")
async def test_browse_delete_returns_204(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户 DELETE 其已有 browse 的 product_id，返回 204 且行被删除。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await delete_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )

    assert result.status_code == 204

    row = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert row is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_delete")
@allure.title("DELETE 无浏览记录的商品返回 404。")
async def test_browse_delete_not_found_returns_404(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """认证用户 DELETE 其无 browse 的 product_id，返回 404。"""
    fake_product_id = str(uuid.uuid4())

    result = await delete_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=fake_product_id,
    )
    assert result.status_code == 404


# ── 401 ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_delete")
@allure.title("未认证访问 DELETE /browse/{product_id} 返回 401。")
async def test_browse_delete_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 DELETE /browse/{product_id} 返回 401。"""
    result = await delete_browse(
        integration_client,
        headers={},
        product_id=str(uuid.uuid4()),
    )
    assert result.status_code == 401
