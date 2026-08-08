"""engagement 域 GET /favorites 分页列表 integration 测试（TDD 红阶段）。

覆盖空列表、items / unavailable_items 分类（reason 枚举）、分页 total、
``created_at`` 降序，以及未上架商品可 POST（201/200 幂等）。
"""

from datetime import UTC, datetime, timedelta

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Shop
from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.db.engagement import seed_favorite
from tests.testkit.helper.engagement import add_favorite, list_favorites
from tests.testkit.helper.ordering import arrange_purchasable_product
from tests.testkit.utils import bearer_headers, decode_jwt_sub

# ── GET /favorites ───────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("空收藏列表返回空 items/unavailable_items 与 total=0。")
async def test_empty_favorites_list_returns_empty(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """无 favorite 行时 GET /favorites 返回空列表与默认分页字段。"""
    result = await list_favorites(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body["items"] == []
    assert result.body["unavailable_items"] == []
    assert result.body["total"] == 0
    assert result.body["limit"] == 20
    assert result.body["offset"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("可展示收藏进入 items，仅含 favorite 元数据。")
async def test_favorites_list_available_in_items(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在、已上架且店铺 active 的收藏进入 items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="99.00",
        name="available-product",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await list_favorites(
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
    assert "created_at" in item
    # item 不含嵌套 product 详情（展示由前端调公开 catalog API）
    assert "price" not in item
    assert "image_url" not in item
    assert "name" not in item


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("未上架商品进入 unavailable_items，reason 为 product_unpublished。")
async def test_favorites_list_unpublished_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在但 is_published=false 的收藏进入 unavailable_items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="unpublished-product",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await list_favorites(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    assert result.body["items"] == []
    unavailable = result.body["unavailable_items"]
    assert len(unavailable) == 1
    item = unavailable[0]
    assert item["product_id"] == product_id
    assert item["reason"] == "product_unpublished"
    assert item["product_name"] == "unpublished-product"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("店铺关闭商品进入 unavailable_items，reason 为 shop_closed。")
async def test_favorites_list_closed_shop_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对应商品存在但所属店铺 status=closed 的收藏进入 unavailable_items。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=True,
        name="closed-shop-product",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    # 关闭店铺（DB 直写）
    await db_session.execute(
        update(Shop).where(Shop.id == shop_owner.shop_id).values(status="closed")
    )
    await db_session.flush()

    result = await list_favorites(
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
@allure.feature("favorites_list")
@allure.title("商品不存在进入 unavailable_items，reason 为 not_found。")
async def test_favorites_list_not_found_in_unavailable(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    authenticated_user: AuthContext,
) -> None:
    """favorite 的 product_id 在 catalog 无对应行时进入 unavailable_items。"""
    user_id = decode_jwt_sub(authenticated_user.access_token)
    fake_product_id = "00000000-0000-4000-8000-000000000000"
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=fake_product_id,
    )

    result = await list_favorites(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    unavailable = result.body["unavailable_items"]
    match = next((i for i in unavailable if i["product_id"] == fake_product_id), None)
    assert match is not None
    assert match["reason"] == "not_found"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("分页 total 计全部 favorite 行（含 unavailable）。")
async def test_favorites_list_pagination_total_counts_all(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """total 为该用户全部 favorite 行数（含 unavailable），不受 limit 影响。"""
    # 2 条可展示 + 1 条未上架
    _, available_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="pagination-a",
    )
    _, available_b = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="pagination-b",
    )
    _, unpublished = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="pagination-unpublished",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=available_a,
    )
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=available_b,
    )
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=unpublished,
    )

    result = await list_favorites(
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
    page2 = await list_favorites(
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
@allure.feature("favorites_list")
@allure.title("列表按收藏时间 created_at 降序。")
async def test_favorites_list_created_at_desc(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """items 按 created_at 降序：最新收藏在前。"""
    _, old_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="desc-old",
    )
    _, new_product = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        name="desc-new",
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    now = datetime.now(UTC)
    # 先 seed 旧收藏、再 seed 新收藏，使插入顺序与 created_at 相反：
    # 实现若按插入顺序而非 created_at DESC 排序，本测试会失败。
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=old_product,
        created_at=now - timedelta(hours=2),
    )
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=new_product,
        created_at=now - timedelta(hours=1),
    )

    result = await list_favorites(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    items = result.body["items"]
    assert [i["product_id"] for i in items] == [new_product, old_product]


# ── 未上架商品可收藏 ─────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("未上架商品可收藏（POST 返回 201/200）。")
async def test_unpublished_product_can_be_favorited(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """存在但 is_published=false 的商品允许收藏（偏好 ≠ 可购）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
        name="favoritable-unpublished",
    )

    result = await add_favorite(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )
    # 首次收藏 201（或幂等 200）
    assert result.status_code in (200, 201)


# ── 401 ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_list")
@allure.title("未认证访问 GET /favorites 返回 401。")
async def test_favorites_list_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 GET /favorites 返回 401。"""
    r = await integration_client.get("/favorites")
    assert r.status_code == 401
