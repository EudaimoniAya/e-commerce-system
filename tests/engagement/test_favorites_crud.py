"""engagement 域收藏 CRUD integration 测试（TDD 红阶段）。

覆盖 ``POST /favorites``（201/200 幂等/422）与 ``DELETE /favorites/{product_id}``
（204/404），以及未认证 401。
"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.engagement import seed_favorite
from tests.support.helper.engagement import add_favorite, delete_favorite
from tests.support.helper.ordering import arrange_purchasable_product
from tests.support.utils import bearer_headers, decode_jwt_sub


# ── POST /favorites ──────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("认证用户首次收藏成功，返回 201。")
async def test_add_favorite_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户首次收藏可购商品成功，返回 201。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    result = await add_favorite(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )
    assert result.status_code == 201
    assert result.body is not None
    assert "id" in result.body
    uuid.UUID(result.body["id"])
    assert result.body["product_id"] == product_id
    assert "created_at" in result.body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("重复收藏同一商品幂等，返回 200 与既有 favorite。")
async def test_add_favorite_duplicate_is_idempotent(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """重复收藏同一商品返回 200，不创建重复行，返回既有 favorite 信息。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    headers = bearer_headers(authenticated_user.access_token)

    first = await add_favorite(
        integration_client,
        headers=headers,
        product_id=product_id,
    )
    assert first.status_code == 201
    assert first.body is not None
    first_id = first.body["id"]

    second = await add_favorite(
        integration_client,
        headers=headers,
        product_id=product_id,
    )
    assert second.status_code == 200
    assert second.body is not None
    assert second.body["id"] == first_id  # 同一行，未新建
    assert second.body["product_id"] == product_id


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("收藏不存在的商品返回 422。")
async def test_add_favorite_product_not_found_returns_422(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """收藏 catalog 中不存在的 product_id 返回 422，且不创建 favorite。"""
    fake_product_id = str(uuid.uuid4())

    result = await add_favorite(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=fake_product_id,
    )
    assert result.status_code == 422


# ── DELETE /favorites/{product_id} ───────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("认证用户取消已收藏商品成功，返回 204。")
async def test_delete_favorite_returns_204(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户 DELETE 其已收藏的 product_id，返回 204 并删除行。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    result = await delete_favorite(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=product_id,
    )
    assert result.status_code == 204


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("DELETE 未收藏的商品返回 404。")
async def test_delete_favorite_not_found_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证用户 DELETE 其未收藏的 product_id，返回 404。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    user_id = decode_jwt_sub(authenticated_user.access_token)
    await seed_favorite(
        db_session,
        user_id=user_id,
        product_id=product_id,
    )

    # 删除另一个未收藏的商品
    fake_product_id = str(uuid.uuid4())
    result = await delete_favorite(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        product_id=fake_product_id,
    )
    assert result.status_code == 404


# ── 401 ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("engagement")
@allure.feature("favorites_crud")
@allure.title("未认证访问 favorites CRUD 端点均返回 401。")
async def test_favorites_crud_unauthenticated_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证访问 POST/DELETE favorites 端点均返回 401。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )
    fake_product_id = str(uuid.uuid4())

    # POST
    r = await integration_client.post(
        "/favorites",
        json={"product_id": product_id},
    )
    assert r.status_code == 401

    # DELETE
    r = await integration_client.delete(f"/favorites/{fake_product_id}")
    assert r.status_code == 401
