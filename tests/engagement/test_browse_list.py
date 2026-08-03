"""engagement 域 GET /browse 分页列表 integration 测试（TDD 红阶段）。

覆盖空列表、items / unavailable_items 分类（reason 枚举）、分页 total、
``last_viewed_at`` 降序、GET 不删除 unavailable 行、未认证 401。
"""

from datetime import UTC, datetime, timedelta

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Shop
from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.engagement import get_browse_history, seed_browse_history
from tests.support.helper.engagement import list_browse
from tests.support.helper.ordering import arrange_purchasable_product
from tests.support.utils import bearer_headers, decode_jwt_sub


# ── GET /browse ───────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("空浏览列表返回空 items/unavailable_items 与 total=0。")
async def test_browse_list_empty_returns_empty(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """无 browse 行时 GET /browse 返回空列表与默认分页字段。"""
    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body == {
        "items": [],
        "unavailable_items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("可展示浏览进入 items，仅含浏览元数据（无 product 详情）。")
async def test_browse_list_available_in_items(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在、已上架且店铺 active 的 browse 进入 items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="browse-available",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    assert result.body["unavailable_items"] == []
    items = result.body["items"]
    assert len(items) == 1
    item = items[0]
    assert item["product_id"] == product_id
    assert "id" in item
    assert "first_viewed_at" in item
    assert "last_viewed_at" in item
    assert "view_count" in item
    # item 不含嵌套 product 价图详情（展示由前端调公开 catalog API）
    assert "price" not in item
    assert "image_url" not in item
    assert "name" not in item


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("未上架商品进入 unavailable_items，reason 为 product_unpublished。")
async def test_browse_list_unpublished_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在但 is_published=false 的 browse 进入 unavailable_items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="browse-unpublished",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    assert result.body["items"] == []
    unavailable = result.body["unavailable_items"]
    match = next((i for i in unavailable if i["product_id"] == product_id), None)
    assert match is not None
    assert match["reason"] == "product_unpublished"
    assert match["product_name"] == "browse-unpublished"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("店铺关闭商品进入 unavailable_items，reason 为 shop_closed。")
async def test_browse_list_closed_shop_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在但所属店铺 status=closed 的 browse 进入 unavailable_items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=True,
        name="browse-closed-shop",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    # 关闭店铺（DB 直写）
    await db_session.execute(
        update(Shop)
        .where(Shop.id == shop_owner.shop_id)
        .values(status="closed")
    )
    await db_session.flush()

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    unavailable = result.body["unavailable_items"]
    match = next((i for i in unavailable if i["product_id"] == product_id), None)
    assert match is not None
    assert match["reason"] == "shop_closed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("商品不存在进入 unavailable_items，reason 为 not_found。")
async def test_browse_list_not_found_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    authenticated_user: AuthContext,
) -> None:
    """browse 的 product_id 在 catalog 无对应行时进入 unavailable_items。"""
    user_id = decode_jwt_sub(authenticated_user.access_token)
    fake_product_id = "00000000-0000-4000-8000-000000000000"
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=fake_product_id,
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    unavailable = result.body["unavailable_items"]
    match = next((i for i in unavailable if i["product_id"] == fake_product_id), None)
    assert match is not None
    assert match["reason"] == "not_found"
    assert match["product_name"] is None  # 不存在时 MAY 为空


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("分页 total 计全部 browse 行（含 unavailable）。")
async def test_browse_list_pagination_total_counts_all(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """total 为该用户全部 browse 行数（含 unavailable），不受 limit 影响。"""
    # 2 条可展示 + 1 条未上架
    _, available_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="browse-pagination-a",
    )
    _, available_b = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="browse-pagination-b",
    )
    _, unpublished = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="browse-pagination-unpublished",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=available_a,
    )
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=available_b,
    )
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=unpublished,
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        limit=2,
    )
    assert result.status_code == 200
    assert result.body is not None

    assert result.body["total"] == 3  # 全部行，不受 limit 截断
    assert result.body["limit"] == 2
    assert len(result.body["items"]) + len(result.body["unavailable_items"]) == 2

    # offset 翻页取到剩余 1 条
    page2 = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        limit=2,
        offset=2,
    )
    assert page2.status_code == 200
    assert page2.body is not None
    assert page2.body["total"] == 3
    assert len(page2.body["items"]) + len(page2.body["unavailable_items"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("列表按 last_viewed_at 降序：最近浏览在前。")
async def test_browse_list_last_viewed_at_desc(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """items 按 last_viewed_at 降序（与插入顺序相反 seed，可区分实现）。"""
    _, old_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="browse-desc-old",
    )
    _, new_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="browse-desc-new",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    now = datetime.now(UTC)
    # 先 seed 旧浏览、再 seed 新浏览，使插入顺序与 last_viewed_at 相反：
    # 实现若按插入顺序而非 last_viewed_at DESC 排序，本测试会失败。
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=old_product,
        last_viewed_at=now - timedelta(hours=2),
    )
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=new_product,
        last_viewed_at=now - timedelta(hours=1),
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    items = result.body["items"]
    assert [i["product_id"] for i in items] == [new_product, old_product]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("GET 不自动删除 unavailable 行：DB 中 browse 行仍存在。")
async def test_browse_list_does_not_delete_unavailable_rows(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """商品下架后 GET /browse 不删除对应 browse 行（清理走 DELETE）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="browse-kept-unavailable",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await list_browse(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    unavailable = result.body["unavailable_items"]
    assert any(i["product_id"] == product_id for i in unavailable)

    row = await get_browse_history(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )
    assert row is not None  # GET 不删除行


# ── 401 ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("browse_list")
@allure.title("未认证访问 GET /browse 返回 401。")
async def test_browse_list_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 GET /browse 返回 401。"""
    result = await list_browse(
        integration_client,
        headers={},
    )
    assert result.status_code == 401
