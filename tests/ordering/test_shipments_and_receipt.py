"""ordering 域 shipments / confirm-receipt integration 测试（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.testkit.helper.auth import register_user_via_otp
from tests.testkit.helper.ordering import (
    arrange_confirmed_order,
    arrange_purchasable_product,
    confirm_receipt,
    create_order,
    create_shipment,
)
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("本店店主对 confirmed 订单发货成功，返回 201 且 status=shipped。")
async def test_create_shipment_by_shop_owner_returns_201(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """本店店主对 confirmed 订单发货成功，返回 201 且 status=shipped。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=paid.body.id,
    )

    assert shipped.status_code == 201
    assert shipped.body is not None
    assert shipped.body.status == "shipped"
    assert shipped.body.id == paid.body.id


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("非本店店主发货返回 404（不泄漏存在性）。")
async def test_create_shipment_non_owner_returns_404(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """非本店店主发货返回 404（design Decision 4c 归属失败统一 404）。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None

    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201
    assert other_user.body is not None

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(other_user.body.access_token),
        order_id=paid.body.id,
    )

    assert shipped.status_code == 404
    assert shipped.body is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("对非 confirmed（awaiting_payment）订单发货返回 409。")
async def test_create_shipment_not_confirmed_returns_409(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对非 confirmed（awaiting_payment）订单发货返回 409。"""
    category_id, product_id = await arrange_purchasable_product(
        db_session,
        shop_id=shop_owner.shop_id,
        stock=10,
    )

    created = await create_order(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        items=[(product_id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None
    assert created.body.status == "awaiting_payment"

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=created.body.id,
    )

    assert shipped.status_code == 409
    assert shipped.body is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("未认证发货返回 401。")
async def test_create_shipment_unauthenticated_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证发货返回 401。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None

    response: Response = await integration_client.post(
        f"/orders/{paid.body.id}/shipments",
        json={},
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("买家对 shipped 订单确认收货，返回 200 且 status=completed。")
async def test_confirm_receipt_returns_200_completed(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家对 shipped 订单确认收货，返回 200 且 status=completed。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201
    assert shipped.body is not None
    assert shipped.body.status == "shipped"

    completed = await confirm_receipt(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        order_id=paid.body.id,
    )

    assert completed.status_code == 200
    assert completed.body is not None
    assert completed.body.status == "completed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ordering")
@allure.feature("shipments_and_receipt")
@allure.title("未认证确认收货返回 401。")
async def test_confirm_receipt_unauthenticated_returns_401(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证确认收货返回 401。"""
    category_id, product_id, paid = await arrange_confirmed_order(
        db_session,
        integration_client,
        shop_id=shop_owner.shop_id,
        buyer_headers=bearer_headers(authenticated_user.access_token),
    )
    assert paid is not None
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201

    response: Response = await integration_client.post(
        f"/orders/{paid.body.id}/confirm-receipt"
    )

    assert response.status_code == 401
