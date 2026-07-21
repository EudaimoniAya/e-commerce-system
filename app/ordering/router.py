"""ordering 域 HTTP 路由（订单 CRUD、状态迁移、列表）。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.catalog.deps import get_current_shop, get_shop_service
from app.catalog.models import Shop
from app.catalog.service import ShopService
from app.infra.auth import get_current_user_id
from app.ordering.deps import (
    get_order_by_id,
    get_order_for_buyer,
    get_order_for_buyer_or_shop,
    get_order_service,
)
from app.ordering.models import Order
from app.ordering.schemas import (
    OrderCreate,
    OrderResponse,
    PaginatedOrders,
    ShipmentCreate,
)
from app.ordering.service import OrderService

router = APIRouter()

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def _to_response(order: Order) -> OrderResponse:
    """ORM Order → OrderResponse（含 items）。"""
    return OrderResponse(
        id=str(order.id),
        buyer_user_id=str(order.buyer_user_id),
        shop_id=str(order.shop_id),
        status=order.status,  # type: ignore[arg-type]
        cancel_reason=order.cancel_reason,
        total_amount=str(order.total_amount),
        expires_at=order.expires_at,
        items=[
            {
                "id": str(i.id),
                "product_id": str(i.product_id),
                "product_name": i.product_name,
                "unit_price": str(i.unit_price),
                "qty": i.qty,
            }
            for i in getattr(order, "items", [])
        ],
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _parse_items_from_create(
    data: OrderCreate,
) -> list[tuple[str, int]]:
    """将 OrderCreate 转为 service 层统一 (product_id, qty) 元组列表。"""
    return [(item.product_id, item.qty) for item in data.items]


def _clamp_pagination(
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    """限制分页参数范围。"""
    return limit, offset


# ── 创建订单 ─────────────────────────────────────────────

@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
async def create_order(
    body: OrderCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """买家下单：同店多行 → 校验 → 预留库存 → 建单。"""
    items = _parse_items_from_create(body)
    order = await service.create_order(user_id, items)
    return _to_response(order)


# ── 买家列表 ─────────────────────────────────────────────

@router.get(
    "/orders",
    response_model=PaginatedOrders,
    tags=["orders"],
)
async def list_my_orders(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
    pagination: tuple[int, int] = Depends(_clamp_pagination),
) -> PaginatedOrders:
    """买家分页查看自己的订单。"""
    limit, offset = pagination
    orders, total = await service.list_buyer_orders(
        user_id, limit=limit, offset=offset,
    )
    return PaginatedOrders(
        items=[_to_response(o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── 订单详情 ─────────────────────────────────────────────

@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    tags=["orders"],
)
async def get_order(
    order: Order = Depends(get_order_for_buyer_or_shop),
) -> OrderResponse:
    """买家或本店店主查看订单详情（触发懒释放）。"""
    return _to_response(order)


# ── 支付桩 ───────────────────────────────────────────────

@router.post(
    "/orders/{order_id}/pay",
    response_model=OrderResponse,
    tags=["orders"],
)
async def pay_order(
    order: Order = Depends(get_order_by_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """买家支付桩：awaiting_payment → confirmed。"""
    if str(order.buyer_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the buyer can pay for this order",
        )
    order = await service.pay_order(order)
    return _to_response(order)


# ── 发货 ─────────────────────────────────────────────────

@router.post(
    "/orders/{order_id}/shipments",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
async def create_shipment(
    body: ShipmentCreate,
    order: Order = Depends(get_order_by_id),
    service: OrderService = Depends(get_order_service),
    user_id: uuid.UUID = Depends(get_current_user_id),
    catalog_service: ShopService = Depends(get_shop_service),
) -> OrderResponse:
    """店主发货：confirmed → shipped。"""
    try:
        shop = await catalog_service.get_my_shop(user_id)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your shop's order",
        )
    if str(order.shop_id) != str(shop.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your shop's order",
        )
    order = await service.create_shipment(order, note=body.note)
    return _to_response(order)


# ── 确认收货 ─────────────────────────────────────────────

@router.post(
    "/orders/{order_id}/confirm-receipt",
    response_model=OrderResponse,
    tags=["orders"],
)
async def confirm_receipt(
    order: Order = Depends(get_order_for_buyer),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """买家确认收货：shipped → completed。"""
    order = await service.confirm_receipt(order)
    return _to_response(order)


# ── 取消订单 ─────────────────────────────────────────────

@router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
    tags=["orders"],
)
async def cancel_order(
    order: Order = Depends(get_order_for_buyer_or_shop),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """买家或店主取消订单（awaiting_payment / confirmed / shipped → cancelled）。"""
    is_buyer = str(order.buyer_user_id) == str(user_id)
    cancel_reason = "buyer_cancelled" if is_buyer else "seller_cancelled"
    order = await service.cancel_order(order, cancel_reason)
    return _to_response(order)


# ── 店主订单列表 ─────────────────────────────────────────

@router.get(
    "/shops/me/orders",
    response_model=PaginatedOrders,
    tags=["orders"],
)
async def list_shop_orders(
    current_shop: Shop = Depends(get_current_shop),
    service: OrderService = Depends(get_order_service),
    pagination: tuple[int, int] = Depends(_clamp_pagination),
) -> PaginatedOrders:
    """店主分页查看本店所有订单。"""
    limit, offset = pagination
    orders, total = await service.list_shop_orders(
        current_shop.id, limit=limit, offset=offset,
    )
    return PaginatedOrders(
        items=[_to_response(o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )
