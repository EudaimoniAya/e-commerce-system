"""ordering 域 HTTP 路由（订单 CRUD、状态迁移、列表）。"""

import uuid

from fastapi import APIRouter, Depends, status

from app.infra.auth import get_current_user_id
from app.infra.pagination.deps import get_pagination_params
from app.infra.pagination.schemas import PaginationParams
from app.ordering.deps import (
    get_order_by_id,
    get_order_for_buyer,
    get_order_for_buyer_or_shop,
    get_order_service,
)
from app.ordering.models import Order
from app.ordering.schemas import (
    BatchPayRequest,
    BatchPayResponse,
    OrderCreate,
    OrderResponse,
    PaginatedOrders,
    SellerOrderCreate,
    ShipmentCreate,
)
from app.ordering.service import OrderService

router = APIRouter()


def _parse_items_from_create(
    data: OrderCreate,
) -> list[tuple[str, int]]:
    """将 OrderCreate 转为 service 层统一 (product_id, qty) 元组列表。"""
    return [(item.product_id, item.qty) for item in data.items]


def _parse_items_from_seller_create(
    data: SellerOrderCreate,
) -> tuple[uuid.UUID, list[tuple[str, int]]]:
    """将 SellerOrderCreate 转为 (buyer_user_id, items) 元组。"""
    return uuid.UUID(data.buyer_user_id), [
        (item.product_id, item.qty) for item in data.items
    ]


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
    return await service.create_order(user_id, items)


# ── 卖家建单 ─────────────────────────────────────────────


@router.post(
    "/shops/me/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
async def create_order_by_seller(
    body: SellerOrderCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """卖家为指定买家建单：校验买家存在且 active → 商品属本店 → 建单。"""
    buyer_user_id, items = _parse_items_from_seller_create(body)
    return await service.create_order_by_seller(
        user_id,
        buyer_user_id,
        items,
    )


# ── 买家列表 ─────────────────────────────────────────────


@router.get(
    "/orders",
    response_model=PaginatedOrders,
    tags=["orders"],
)
async def list_my_orders(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> PaginatedOrders:
    """买家分页查看自己的订单。"""
    return await service.list_buyer_orders(
        user_id,
        limit=params.limit,
        offset=params.offset,
    )


# ── 订单详情 ─────────────────────────────────────────────


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    tags=["orders"],
)
async def get_order(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """买家或本店店主查看订单详情（触发懒释放 + 鉴权 + 映射）。

    deps 只解析 user_id（未认证 401）；fetch/鉴权/schema 全由 service 产出。
    """
    return await service.get_order_response(order_id, user_id)


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
    return await service.pay_order(user_id, order)


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
) -> OrderResponse:
    """店主发货：confirmed → shipped。"""
    return await service.create_shipment(user_id, order, note=body.note)


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
    return await service.confirm_receipt(order)


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
    return await service.cancel_order(user_id, order)


# ── 店主订单列表 ─────────────────────────────────────────


@router.get(
    "/shops/me/orders",
    response_model=PaginatedOrders,
    tags=["orders"],
)
async def list_shop_orders(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> PaginatedOrders:
    """店主分页查看本店所有订单。"""
    return await service.list_shop_orders(
        user_id,
        limit=params.limit,
        offset=params.offset,
    )


# ── 批量支付 ──────────────────────────────────────────────


@router.post(
    "/orders/batch-pay",
    response_model=BatchPayResponse,
    tags=["orders"],
)
async def batch_pay(
    body: BatchPayRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> BatchPayResponse:
    """批量支付桩：全有或全无，单事务。"""
    order_ids = [uuid.UUID(oid) for oid in body.order_ids]
    return await service.batch_pay_orders(
        user_id=user_id,
        order_ids=order_ids,
    )
