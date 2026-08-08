"""ordering 域 GET /cart integration 测试（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.ordering import seed_cart_item
from tests.support.helper.catalog import register_and_open_shop
from tests.support.helper.ordering import arrange_purchasable_product, get_cart
from tests.support.utils import bearer_headers, decode_jwt_sub


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("空购物车返回 shops:[] 与 invalid_items:[]。")
async def test_empty_cart_returns_shops_and_invalid_items_empty(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """空购物车返回 shops:[] 与 invalid_items:[]。"""
    result = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body["shops"] == []
    assert result.body["invalid_items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("多店 cart 行按 shop_id 分组展示。")
async def test_cart_list_grouped_by_shop(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """多店 cart 行按 shop_id 分组展示。"""
    # Arrange: shop_owner 的店 + 另一个店
    _, product_a = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="10.00",
        name="product-a",
    )

    other_reg, other_shop = await register_and_open_shop(integration_client)
    assert other_shop is not None and other_shop.status_code == 201
    _, product_b = await arrange_purchasable_product(
        db_session,
        shop_id=other_shop.body.id,
        stock=10,
        price="20.00",
        name="product-b",
    )

    # TODO(green): use actual user UUID instead of placeholder
    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_a,
        qty=2,
    )
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_b,
        qty=1,
    )

    result = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    shops = result.body["shops"]
    assert len(shops) == 2
    shop_ids = {s["shop_id"] for s in shops}
    assert shop_owner.shop_id in shop_ids
    assert other_shop.body.id in shop_ids

    # 每个 shop 的 items 含 cart_item_id、product_id、qty、实时价
    for shop in shops:
        for item in shop["items"]:
            assert "cart_item_id" in item
            assert "product_id" in item
            assert "qty" in item
            assert "unit_price" in item


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("未上架商品进入 invalid_items，不自动删除。")
async def test_cart_list_invalid_items_unpublished_product(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未上架商品进入 invalid_items，不自动删除。"""
    # 创建未上架商品
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_id,
        qty=1,
    )

    result = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    assert len(result.body["shops"]) == 0
    invalid = result.body["invalid_items"]
    assert len(invalid) >= 1
    assert any(i["product_id"] == product_id for i in invalid), (
        f"product {product_id} should be in invalid_items"
    )


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("关店商品进入 invalid_items，reason 为 shop_closed。")
async def test_cart_list_invalid_items_closed_shop(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """关店商品进入 invalid_items，reason 为 shop_closed。"""
    # 创建 active 商品，但之后 shop 会被 close（通过 DB 直接改）
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=True,
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_id,
        qty=1,
    )

    # 关闭店铺（DB 直写）
    from sqlalchemy import update

    from app.catalog.models import Shop

    await db_session.execute(
        update(Shop).where(Shop.id == shop_owner.shop_id).values(status="closed")
    )
    await db_session.flush()

    result = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    invalid = result.body["invalid_items"]
    assert len(invalid) >= 1
    match = next((i for i in invalid if i["product_id"] == product_id), None)
    assert match is not None
    assert match["reason"] == "shop_closed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("cart 列表展示 catalog 实时价（非快照）。")
async def test_cart_list_real_time_price(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """cart 列表展示 catalog 实时价（非快照）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        price="99.00",
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_id,
        qty=1,
    )

    # 改价
    from decimal import Decimal

    from sqlalchemy import update

    from app.catalog.models import Product

    await db_session.execute(
        update(Product).where(Product.id == product_id).values(price=Decimal("149.00"))
    )
    await db_session.flush()

    result = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result.status_code == 200
    assert result.body is not None

    shops = result.body["shops"]
    assert len(shops) == 1
    item = shops[0]["items"][0]
    assert item["unit_price"] == "149.00"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("失效行仅在列表展示，不自动从 cart_items 表删除。")
async def test_cart_list_no_auto_delete_invalid(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """失效行仅在列表展示，不自动从 cart_items 表删除。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
        is_published=False,
    )

    user_id_placeholder = decode_jwt_sub(authenticated_user.access_token)
    await seed_cart_item(
        db_session,
        user_id=user_id_placeholder,
        product_id=product_id,
        qty=1,
    )

    # 第一次 GET：出现在 invalid_items
    result1 = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result1.status_code == 200
    assert len(result1.body["invalid_items"]) >= 1

    # 第二次 GET：仍然在 invalid_items（未被删除）
    result2 = await get_cart(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
    )
    assert result2.status_code == 200
    assert len(result2.body["invalid_items"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_list")
@allure.title("未认证访问 GET /cart 返回 401。")
async def test_cart_list_unauthenticated_returns_401(
    integration_client: AsyncClient,
) -> None:
    """未认证访问 GET /cart 返回 401。"""
    r = await integration_client.get("/cart")
    assert r.status_code == 401
