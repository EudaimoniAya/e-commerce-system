"""support 域 message_refs 校验 integration 测试（TDD 红阶段）。

覆盖：纯 product ref 无 body 201、跨 shop product ref 422、未上架本店商品 ref 201、
order ref 422、去重后 refs>10 422、重复 ref 去重后允许、响应仅含 {ref_type, ref_id}。
"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.db.catalog import seed_product
from tests.support.helper.ordering import arrange_purchasable_product
from tests.support.helper.support import post_buyer_message
from tests.support.utils import bearer_headers


def _product_ref(product_id: str) -> dict[str, str]:
    return {"ref_type": "product", "ref_id": product_id}


async def _seed_products(
    db_session: AsyncSession,
    *,
    shop_id: str,
    count: int,
    is_published: bool = True,
) -> list[str]:
    """Arrange：为店铺直写 N 个商品（不经 HTTP），返回 product_id 列表。"""
    ids: list[str] = []
    for i in range(count):
        product_id = await seed_product(
            db_session,
            shop_id=shop_id,
            name=f"ref-{i}-{uuid.uuid4().hex[:8]}",
            is_published=is_published,
        )
        ids.append(product_id)
    return ids


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("纯 product ref 无 body 返回 201。")
async def test_message_refs_pure_product_ref_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """仅含合法本店 product ref、无 body 的 POST 返回 201。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
    )

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )

    assert result.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("跨 shop 商品 ref 返回 422。")
async def test_message_refs_cross_shop_product_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """product ref 不属于该会话 shop 时返回 422。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
    )

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=second_shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )

    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("未上架本店商品 ref 返回 201。")
async def test_message_refs_unpublished_shop_product_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """引用本 shop 内 is_published=false 的商品返回 201（不按公开可见性过滤）。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        is_published=False,
    )

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )

    assert result.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("order ref 返回 422。")
async def test_message_refs_order_ref_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """MVP 收到 ref_type=order 返回 422。"""
    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=[{"ref_type": "order", "ref_id": str(uuid.uuid4())}],
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("去重后 refs 超过 10 返回 422。")
async def test_message_refs_over_ten_distinct_returns_422(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """11 个不同本店 product ref 去重后仍 >10，返回 422。"""
    product_ids = await _seed_products(
        db_session,
        shop_id=shop_owner.shop_id,
        count=11,
    )
    refs = [_product_ref(pid) for pid in product_ids]

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=refs,
    )

    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("重复 (ref_type, ref_id) 去重后允许（15 个相同 ref 返回 201）。")
async def test_message_refs_duplicates_deduped_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """15 个重复的相同 product ref 去重后计数为 1（≤10），返回 201。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
    )
    refs = [_product_ref(product_id) for _ in range(15)]

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=refs,
    )

    assert result.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("message_refs")
@allure.title("响应 refs 仅含 ref_type/ref_id，不 enrich 商品详情。")
async def test_message_refs_response_only_ref_type_and_id(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """POST 后响应中 message_refs 每项键恰为 {ref_type, ref_id}。"""
    _, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
    )

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )

    assert result.status_code == 201
    assert result.body is not None
    assert result.body["message_refs"] == [_product_ref(product_id)]
