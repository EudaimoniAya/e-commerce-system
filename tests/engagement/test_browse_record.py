"""engagement 域 POST /browse integration 测试（TDD 红阶段）。

覆盖 202 受理（BackgroundTasks 落库 await DB）、422 商品不存在（不调度后台）、
未上架商品允许记录、debounce 内 view_count 不 +1、活跃期间递增 / 间断重置、401。
"""

import uuid
from datetime import UTC, datetime, timedelta

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.engagement import get_browse_history, seed_browse_history
from tests.support.helper.engagement import record_browse
from tests.support.helper.ordering import arrange_purchasable_product
from tests.support.utils import bearer_headers, decode_jwt_sub

# ── POST /browse ──────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("首次浏览受理：202 + accepted=true，后台落库 view_count=1。")
async def test_browse_record_first_view_accepted_202(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户 POST 存在商品返回 202；helper 返回时后台 upsert 已完成（await DB）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    headers = bearer_headers(authenticated_user.access_token)

    result = await record_browse(
        integration_client,
        headers=headers,
        product_id=product_id,
    )

    assert result.status_code == 202
    assert result.body == {"accepted": True}

    row = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert row is not None
    assert row["view_count"] == 1
    assert row["first_viewed_at"] <= row["last_viewed_at"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("POST 不存在的商品返回 422，且不调度后台（无 browse 行）。")
async def test_browse_record_product_not_found_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    authenticated_user: AuthContext,
) -> None:
    """catalog 中不存在的 product_id 返回 422，且 SHALL NOT 创建 browse 行。"""
    fake_product_id = str(uuid.uuid4())
    user_id = decode_jwt_sub(authenticated_user.access_token)

    result = await record_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=fake_product_id,
    )

    assert result.status_code == 422

    row = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=fake_product_id,
    )
    assert row is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("未上架商品允许记录浏览：202 且后台 upsert browse 行。")
async def test_browse_record_unpublished_product_accepted_202(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """存在但 is_published=false 的商品仍允许记录浏览（足迹 ≠ 可购）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)

    result = await record_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )

    assert result.status_code == 202

    row = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert row is not None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("debounce 内重复 POST：view_count 不变，last_viewed_at 仍更新。")
async def test_browse_record_debounce_does_not_increment_view_count(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """已有 browse 行且距上次浏览在 debounce 窗口内：view_count 不 +1。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    now = datetime.now(UTC)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
        last_viewed_at=now - timedelta(seconds=3),
        view_count=7,
    )
    before = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert before is not None

    result = await record_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )

    assert result.status_code == 202

    after = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert after is not None
    assert after["view_count"] == 7  # debounce 内不 +1
    assert after["last_viewed_at"] >= before["last_viewed_at"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("活跃期间重复 POST：view_count 递增 +1，last_viewed_at 更新。")
async def test_browse_record_active_view_count_increments(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """debounce 已过期且距上次浏览未超 retention：view_count 为原值 + 1。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    now = datetime.now(UTC)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
        last_viewed_at=now - timedelta(hours=1),
        view_count=7,
    )

    result = await record_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )

    assert result.status_code == 202

    after = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert after is not None
    assert after["view_count"] == 8
    # DB 读回为 naive 墙钟（asyncmy 对 DATETIME 必返 naive）；now 为 aware，需剥 tz 后比较
    assert after["last_viewed_at"] > now.replace(tzinfo=None) - timedelta(hours=1)


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("间断超 retention 后 POST：view_count 重置为 1，first_viewed_at 不变。")
async def test_browse_record_gap_resets_view_count(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """距上次浏览超过 retention 后再次 POST：view_count 重置为 1，first_viewed_at 保持首次。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    now = datetime.now(UTC)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
        first_viewed_at=now - timedelta(days=40),
        last_viewed_at=now - timedelta(days=40),
        view_count=7,
    )
    before = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert before is not None

    result = await record_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )

    assert result.status_code == 202

    after = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert after is not None
    assert after["view_count"] == 1  # 间断重置累计
    assert after["first_viewed_at"] == before["first_viewed_at"]  # 首次时间不变


# ── 401 ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_record")
@allure.title("未认证 POST /browse 返回 401。")
async def test_browse_record_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 POST /browse 返回 401。"""
    result = await record_browse(
        integration_client,
        headers={},
        product_id=str(uuid.uuid4()),
    )
    assert result.status_code == 401
