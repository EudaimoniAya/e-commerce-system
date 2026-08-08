"""ordering 域 cart CRUD integration 测试（TDD 红阶段）。"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.ordering import seed_cart_item
from tests.support.helper.ordering import (
    add_cart_item,
    arrange_purchasable_product,
    delete_cart_item,
    patch_cart_item,
)
from tests.support.utils import bearer_headers, decode_jwt_sub

# ── POST /cart/items ──────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("认证用户加购可购商品成功，返回 201。")
async def test_add_cart_item_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户加购可购商品成功，返回 201。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    result = await add_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
        qty=3,
    )
    assert result.status_code == 201
    assert result.body is not None
    assert "id" in result.body
    uuid.UUID(result.body["id"])
    assert result.body["product_id"] == product_id
    assert result.body["qty"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("加购不存在的商品返回 422。")
async def test_add_cart_item_product_not_found_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """加购不存在的商品返回 422。"""
    fake_product_id = str(uuid.uuid4())

    result = await add_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=fake_product_id,
        qty=1,
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("重复加购同一商品累加 qty，不报错。")
async def test_add_cart_item_duplicate_product_accumulates_qty(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """重复加购同一商品累加 qty，不报错。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    # 首次加购 qty=2
    first = await add_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
        qty=2,
    )
    assert first.status_code == 201
    assert first.body is not None
    assert first.body["qty"] == 2
    first_id = first.body["id"]

    # 重复加购 qty=5 → 200，qty 累加为 7
    second = await add_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
        qty=5,
    )
    assert second.status_code == 200
    assert second.body is not None
    assert second.body["qty"] == 7
    assert second.body["id"] == first_id  # 同一行


# ── PATCH /cart/items/{id} ─────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("认证用户修改本人 cart item 数量成功，返回 200。")
async def test_patch_cart_item_updates_qty_returns_200(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户修改本人 cart item 数量成功，返回 200。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    cart_item_id = await seed_cart_item(
        db_session,
        user_id=decode_jwt_sub(
            authenticated_user.access_token
        ),  # 注：seed 需 user_id，此处用 token 作为占位
        product_id=product_id,
        qty=1,
    )
    # 实际 user_id 应为注册用户的 UUID——在绿阶段接入 UserService 后修正

    result = await patch_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=cart_item_id,
        qty=5,
    )
    assert result.status_code == 200
    assert result.body is not None
    assert result.body["qty"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("PATCH 不存在的 cart_item id 返回 404。")
async def test_patch_cart_item_not_found_returns_404(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """PATCH 不存在的 cart_item id 返回 404。"""
    fake_id = str(uuid.uuid4())

    result = await patch_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=fake_id,
        qty=5,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("PATCH 他人 cart item 返回 404（不暴露存在性）。")
async def test_patch_other_user_cart_item_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """PATCH 他人 cart item 返回 404（不暴露存在性）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    other_user_id = decode_jwt_sub(shop_owner.access_token)
    cart_item_id = await seed_cart_item(
        db_session,
        user_id=other_user_id,
        product_id=product_id,
        qty=1,
    )

    result = await patch_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=cart_item_id,
        qty=5,
    )
    assert result.status_code == 404


# ── DELETE /cart/items/{id} ────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("认证用户删除本人 cart item 成功，返回 204。")
async def test_delete_cart_item_returns_204(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户删除本人 cart item 成功，返回 204。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    cart_item_id = await seed_cart_item(
        db_session,
        user_id=decode_jwt_sub(authenticated_user.access_token),
        product_id=product_id,
        qty=1,
    )

    result = await delete_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=cart_item_id,
    )
    assert result.status_code == 204


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("DELETE 不存在的 cart_item id 返回 404。")
async def test_delete_cart_item_not_found_returns_404(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """DELETE 不存在的 cart_item id 返回 404。"""
    fake_id = str(uuid.uuid4())

    result = await delete_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=fake_id,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("DELETE 他人 cart item 返回 404（不暴露存在性）。")
async def test_delete_other_user_cart_item_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """DELETE 他人 cart item 返回 404（不暴露存在性）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    other_user_id = decode_jwt_sub(shop_owner.access_token)
    cart_item_id = await seed_cart_item(
        db_session,
        user_id=other_user_id,
        product_id=product_id,
        qty=1,
    )

    result = await delete_cart_item(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        cart_item_id=cart_item_id,
    )
    assert result.status_code == 404


# ── 401 ────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("cart_crud")
@allure.title("未认证访问 cart 端点均返回 401。")
async def test_cart_crud_unauthenticated_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证访问 cart 端点均返回 401。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    fake_id = str(uuid.uuid4())

    # POST
    r = await integration_client.post(
        "/cart/items",
        json={"product_id": product_id, "qty": 1},
    )
    assert r.status_code == 401

    # PATCH
    r = await integration_client.patch(
        f"/cart/items/{fake_id}",
        json={"qty": 1},
    )
    assert r.status_code == 401

    # DELETE
    r = await integration_client.delete(f"/cart/items/{fake_id}")
    assert r.status_code == 401
