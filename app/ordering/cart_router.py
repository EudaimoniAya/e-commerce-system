"""ordering 域 cart REST 端点。"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from app.infra.auth import get_current_user_id
from app.ordering.cart_service import CartService
from app.ordering.deps import (
    get_cart_service,
    get_current_cart_item,
    get_current_checkout_batch,
)
from app.ordering.models import CartItem, CheckoutBatch
from app.ordering.schemas import (
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartListResponse,
    CheckoutBatchResponse,
    CheckoutRequest,
    CheckoutResponse,
)

router = APIRouter(tags=["cart"])


@router.post("/cart/items", response_model=CartItemResponse)
async def add_cart_item(
    body: CartItemCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> JSONResponse:
    """加购商品（新建→201，已存在→200 累加 qty）。"""
    item, created = await service.add_item(
        user_id=user_id,
        product_id=uuid.UUID(body.product_id),
        qty=body.qty,
    )
    return JSONResponse(
        content=item.model_dump(mode="json"),
        status_code=201 if created else 200,
    )


@router.get("/cart", response_model=CartListResponse)
async def list_cart(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartListResponse:
    """获取购物车列表（按店分组 + invalid_items）。"""
    return await service.list_cart(user_id)


@router.patch("/cart/items/{cart_item_id}", response_model=CartItemResponse)
async def update_cart_item(
    body: CartItemUpdate,
    item: CartItem = Depends(get_current_cart_item),
    service: CartService = Depends(get_cart_service),
) -> CartItemResponse:
    """修改购物车行数量（deps 已鉴权归属）。"""
    return await service.update_qty(item, qty=body.qty)


@router.delete("/cart/items/{cart_item_id}", status_code=204)
async def remove_cart_item(
    item: CartItem = Depends(get_current_cart_item),
    service: CartService = Depends(get_cart_service),
) -> Response:
    """删除购物车行（deps 已鉴权归属）。"""
    await service.delete_item(item)
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


@router.get(
    "/orders/checkout-batches/{batch_id}",
    response_model=CheckoutBatchResponse,
)
async def get_checkout_batch_detail(
    batch: CheckoutBatch = Depends(get_current_checkout_batch),
    service: CartService = Depends(get_cart_service),
) -> CheckoutBatchResponse:
    """查看结算批次详情（deps 已鉴权买家；子订单/聚合/派生状态/schema 由 service 产出）。"""
    return await service.get_checkout_batch(batch)
