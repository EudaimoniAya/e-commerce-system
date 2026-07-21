"""ordering 域 shipments / confirm-receipt integration 测试（TDD 红阶段）。"""

import pytest
from httpx import AsyncClient, Response

from tests.support.contexts import (
    AdminAuthContext,
    AuthContext,
    ShopOwnerContext,
)
from tests.support.helpers import (
    arrange_confirmed_order,
    arrange_purchasable_product,
    confirm_receipt,
    create_order,
    create_shipment,
    register_authenticated,
)
from tests.support.projections import bearer_headers
from tests.support.results import OrderResult, ProductResult, RegisterResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shipment_by_shop_owner_returns_201(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """本店店主对 confirmed 订单发货成功，返回 201 且 status=shipped。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
    )
    paid = arranged.step(OrderResult)
    assert paid.status_code == 200
    assert paid.body is not None
    assert paid.body.status == "confirmed"

    shipped = await create_shipment(
        client,
        headers=bearer_headers(owner),
        order_id=paid.body.id,
    )

    assert shipped.status_code == 201
    assert shipped.body is not None
    assert shipped.body.status == "shipped"
    assert shipped.body.id == paid.body.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shipment_non_owner_returns_403(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """非本店店主发货返回 403。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
    )
    paid = arranged.step(OrderResult)
    assert paid.status_code == 200
    assert paid.body is not None

    other = await register_authenticated(client)
    other_user = other.step(RegisterResult)
    assert other_user.status_code == 201
    assert other_user.body is not None

    shipped = await create_shipment(
        client,
        headers=bearer_headers(other_user),
        order_id=paid.body.id,
    )

    assert shipped.status_code == 403
    assert shipped.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shipment_not_confirmed_returns_409(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对非 confirmed（awaiting_payment）订单发货返回 409。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_purchasable_product(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        stock=10,
    )
    product = arranged.step(ProductResult)
    assert product.status_code == 201
    assert product.body is not None

    created = await create_order(
        client,
        headers=bearer_headers(buyer),
        items=[(product.body.id, 1)],
    )
    assert created.status_code == 201
    assert created.body is not None
    assert created.body.status == "awaiting_payment"

    shipped = await create_shipment(
        client,
        headers=bearer_headers(owner),
        order_id=created.body.id,
    )

    assert shipped.status_code == 409
    assert shipped.body is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_shipment_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证发货返回 401。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
    )
    paid = arranged.step(OrderResult)
    assert paid.status_code == 200
    assert paid.body is not None

    response: Response = await client.post(
        f"/orders/{paid.body.id}/shipments",
        json={},
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirm_receipt_returns_200_completed(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家对 shipped 订单确认收货，返回 200 且 status=completed。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
    )
    paid = arranged.step(OrderResult)
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        client,
        headers=bearer_headers(owner),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201
    assert shipped.body is not None
    assert shipped.body.status == "shipped"

    completed = await confirm_receipt(
        client,
        headers=bearer_headers(buyer),
        order_id=paid.body.id,
    )

    assert completed.status_code == 200
    assert completed.body is not None
    assert completed.body.status == "completed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirm_receipt_unauthenticated_returns_401(
    client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """未认证确认收货返回 401。"""
    buyer = authenticated_user.root.step(RegisterResult)
    assert buyer.status_code == 201
    assert buyer.body is not None
    owner = shop_owner.root.step(RegisterResult)
    assert owner.status_code == 201
    assert owner.body is not None

    arranged = await arrange_confirmed_order(
        client,
        shop_owner=shop_owner.root,
        admin=admin_auth_headers.root,
        buyer_headers=bearer_headers(buyer),
    )
    paid = arranged.step(OrderResult)
    assert paid.status_code == 200
    assert paid.body is not None

    shipped = await create_shipment(
        client,
        headers=bearer_headers(owner),
        order_id=paid.body.id,
    )
    assert shipped.status_code == 201

    response: Response = await client.post(
        f"/orders/{paid.body.id}/confirm-receipt"
    )

    assert response.status_code == 401
