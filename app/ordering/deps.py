"""ordering 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.deps import get_product_service, get_shop_service
from app.catalog.product_service import ProductService
from app.catalog.shop_service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.database import get_db
from app.ordering.cart_repository import CartRepository
from app.ordering.cart_service import CartService
from app.ordering.checkout_batch_repository import CheckoutBatchRepository
from app.ordering.models import Order
from app.ordering.repository import OrderItemRepository, OrderRepository
from app.ordering.service import OrderService
from app.user.deps import get_user_service
from app.user.service import UserService

_NOT_FOUND_MSG = "Order not found"


def get_cart_repository(
    session: AsyncSession = Depends(get_db),
) -> CartRepository:
    """注入购物车仓储。"""
    return CartRepository(session)


def get_checkout_batch_repository(
    session: AsyncSession = Depends(get_db),
) -> CheckoutBatchRepository:
    """注入结算批次仓储。"""
    return CheckoutBatchRepository(session)


def get_order_repository(
    session: AsyncSession = Depends(get_db),
) -> OrderRepository:
    """注入订单仓储。"""
    return OrderRepository(session)


def get_order_item_repository(
    session: AsyncSession = Depends(get_db),
) -> OrderItemRepository:
    """注入订单行仓储。"""
    return OrderItemRepository(session)


def get_order_service(
    session: AsyncSession = Depends(get_db),
    product_service: ProductService = Depends(get_product_service),
    shop_service: ShopService = Depends(get_shop_service),
    order_repo: OrderRepository = Depends(get_order_repository),
    item_repo: OrderItemRepository = Depends(get_order_item_repository),
    user_service: UserService = Depends(get_user_service),
) -> OrderService:
    """注入 ordering 编排服务（共享同一 DB 事务）。"""
    return OrderService(
        session,
        product_service,
        shop_service,
        order_repo,
        item_repo,
        user_service,
    )


def get_cart_service(
    session: AsyncSession = Depends(get_db),
    cart_repo: CartRepository = Depends(get_cart_repository),
    product_service: ProductService = Depends(get_product_service),
    batch_repo: CheckoutBatchRepository = Depends(get_checkout_batch_repository),
    order_service: OrderService = Depends(get_order_service),
) -> CartService:
    """注入购物车编排服务（共享同一 DB 事务；含 checkout 依赖）。"""
    return CartService(session, cart_repo, product_service, batch_repo, order_service)


async def get_order_by_id(
    order_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> Order:
    """按路径参数 order_id 解析订单；不存在时 404；读时触发懒释放。

    先解析 user_id（若未认证 401），再查订单。
    """
    # user_id 先于 order 解析，确保未认证时返回 401 而非 404
    _ = user_id

    order = await service.get_order_or_404(order_id)

    # 读时懒释放（expire_if_needed 内部会 commit 过期变更）
    expired = await service.expire_if_needed(order)
    if expired:
        order = await service.get_order_or_404(order_id)

    return order


async def get_order_for_buyer(
    order: Order = Depends(get_order_by_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Order:
    """买家视角：仅允许买家本人访问自己的订单，否则 404。"""
    if str(order.buyer_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND_MSG,
        )
    return order


async def get_order_for_buyer_or_shop(
    order: Order = Depends(get_order_by_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    shop_service: ShopService = Depends(get_shop_service),
) -> Order:
    """买家或本店店主视角；既不属买家又非店主时 404。"""
    if str(order.buyer_user_id) == str(user_id):
        return order

    try:
        shop = await shop_service.get_my_shop(user_id)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND_MSG,
        ) from None
    if str(shop.id) == str(order.shop_id):
        return order

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_NOT_FOUND_MSG,
    )
