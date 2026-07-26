"""ordering 域 cart REST 端点。"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.infra.auth import get_current_user_id
from app.ordering.cart_service import CartService
from app.ordering.deps import get_cart_service
from app.ordering.schemas import CartItemCreate, CartItemResponse, CartItemUpdate, CartListResponse

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
