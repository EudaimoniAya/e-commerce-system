"""ordering 域 cart REST 端点。"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.infra.auth import get_current_user_id
from app.ordering.cart_service import CartService
from app.ordering.checkout_batch_repository import CheckoutBatchRepository
from app.ordering.deps import (
    get_cart_service,
    get_checkout_batch_repository,
    get_order_repository,
    get_order_service,
)
from app.ordering.repository import OrderRepository
from app.ordering.schemas import (
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartListResponse,
    CheckoutBatchOrder,
    CheckoutBatchOrderItem,
    CheckoutBatchResponse,
    CheckoutBatchShopGroup,
    CheckoutRequest,
    CheckoutResponse,
)
from app.ordering.service import OrderService

router = APIRouter(tags=["cart"])


def _to_cart_item_response(item) -> CartItemResponse:
    """ORM CartItem → CartItemResponse。"""
    return CartItemResponse(
        id=str(item.id),
        user_id=str(item.user_id),
        product_id=str(item.product_id),
        qty=item.qty,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/cart/items", status_code=201, response_model=CartItemResponse)
async def add_cart_item(
    body: CartItemCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartItemResponse:
    """加购商品到购物车。"""
    item = await service.add_item(
        user_id=user_id,
        product_id=uuid.UUID(body.product_id),
        qty=body.qty,
    )
    return _to_cart_item_response(item)


@router.get("/cart", response_model=CartListResponse)
async def list_cart(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartListResponse:
    """获取购物车列表（按店分组 + invalid_items）。"""
    return await service.list_cart(user_id)


@router.patch("/cart/items/{cart_item_id}", response_model=CartItemResponse)
async def update_cart_item(
    cart_item_id: uuid.UUID,
    body: CartItemUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartItemResponse:
    """修改购物车行数量。"""
    item = await service.update_qty(
        user_id=user_id,
        cart_item_id=cart_item_id,
        qty=body.qty,
    )
    return _to_cart_item_response(item)


@router.delete("/cart/items/{cart_item_id}", status_code=204)
async def remove_cart_item(
    cart_item_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> Response:
    """删除购物车行。"""
    await service.delete_item(
        user_id=user_id,
        cart_item_id=cart_item_id,
    )
    return Response(status_code=204)


@router.post("/cart/checkout", status_code=201, response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CheckoutResponse:
    """结算购物车选中行：单事务建 batch + N 子订单 + 删 cart。"""
    cart_item_ids = [uuid.UUID(cid) for cid in body.cart_item_ids]
    return await service.checkout(user_id=user_id, cart_item_ids=cart_item_ids)


# ── Checkout Batch Detail ──────────────────────────────────────


def _derive_batch_status(statuses: set[str]) -> str:
    """读时计算 batch 派生状态。"""
    has_awaiting = "awaiting_payment" in statuses
    has_confirmed = "confirmed" in statuses
    if has_awaiting and not has_confirmed:
        return "pending_payment"
    if has_awaiting and has_confirmed:
        return "partially_paid"
    if not has_awaiting:
        return "closed"
    return "closed"


@router.get(
    "/orders/checkout-batches/{batch_id}",
    response_model=CheckoutBatchResponse,
)
async def get_checkout_batch_detail(
    batch_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    batch_repo: CheckoutBatchRepository = Depends(get_checkout_batch_repository),
    order_repo: OrderRepository = Depends(get_order_repository),
    order_service: OrderService = Depends(get_order_service),
) -> CheckoutBatchResponse:
    """查看结算批次详情（含子订单、聚合金额、派生状态）。"""
    batch = await batch_repo.get_by_id(batch_id)
    if batch is None or str(batch.buyer_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout batch not found",
        )

    orders = await order_repo.list_by_checkout_batch_id(batch_id)
    paid_total = Decimal("0.00")
    remaining_total = Decimal("0.00")
    statuses: set[str] = set()
    shops_map: dict[str, list[CheckoutBatchOrder]] = {}

    for order in orders:
        await order_service.expire_if_needed(order)
        # re-fetch after possible expiry
        refreshed = await order_repo.get_by_id(order.id)
        if refreshed is None:
            continue
        statuses.add(refreshed.status)

        items = await order_service._item_repo.list_by_order_id(refreshed.id)
        item_responses = [
            CheckoutBatchOrderItem(
                id=str(i.id),
                product_id=str(i.product_id),
                product_name=i.product_name,
                unit_price=str(i.unit_price),
                qty=i.qty,
            )
            for i in items
        ]

        order_data = CheckoutBatchOrder(
            id=str(refreshed.id),
            shop_id=str(refreshed.shop_id),
            status=refreshed.status,
            initiated_by=refreshed.initiated_by,
            total_amount=str(refreshed.total_amount),
            expires_at=refreshed.expires_at,
            items=item_responses,
            created_at=refreshed.created_at,
        )

        sid = str(refreshed.shop_id)
        if sid not in shops_map:
            shops_map[sid] = []
        shops_map[sid].append(order_data)

        if refreshed.status == "awaiting_payment":
            remaining_total += refreshed.total_amount
        elif refreshed.status == "confirmed":
            paid_total += refreshed.total_amount

    shops = [
        CheckoutBatchShopGroup(shop_id=sid, orders=ords)
        for sid, ords in shops_map.items()
    ]

    return CheckoutBatchResponse(
        id=str(batch.id),
        buyer_user_id=str(batch.buyer_user_id),
        created_at=batch.created_at,
        shops=shops,
        paid_total=str(paid_total),
        remaining_total=str(remaining_total),
        status=_derive_batch_status(statuses),
    )
