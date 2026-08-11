"""ordering 域 cart 业务逻辑：CRUD + 列表 enrichment + checkout 编排。"""

import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.product_service import ProductService
from app.catalog.schemas import PurchasableProduct
from app.ordering.cart_repository import CartRepository
from app.ordering.checkout_batch_repository import CheckoutBatchRepository
from app.ordering.models import CartItem, CheckoutBatch
from app.ordering.schemas import (
    CartInvalidItem,
    CartItemResponse,
    CartListResponse,
    CartShopGroup,
    CartShopItem,
    CheckoutBatchOrder,
    CheckoutBatchOrderItem,
    CheckoutBatchResponse,
    CheckoutBatchShopGroup,
    CheckoutResponse,
)
from app.ordering.service import OrderService, to_order_response


def _to_cart_item_response(item) -> CartItemResponse:
    """ORM CartItem → CartItemResponse。

    模块级私有映射（与各域 `_to_*` 一致）；schema 归 service 产出，router 不做 ORM 映射。
    """
    return CartItemResponse(
        id=str(item.id),
        user_id=str(item.user_id),
        product_id=str(item.product_id),
        qty=item.qty,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _derive_batch_status(statuses: set[str]) -> str:
    """读时计算 batch 派生状态（随 get_checkout_batch 收进 service）。"""
    has_awaiting = "awaiting_payment" in statuses
    has_confirmed = "confirmed" in statuses
    if has_awaiting and not has_confirmed:
        return "pending_payment"
    if has_awaiting and has_confirmed:
        return "partially_paid"
    return "closed"


class CartService:
    """购物车业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
        cart_repo: CartRepository,
        product_service: ProductService,
        batch_repo: CheckoutBatchRepository,
        order_service: OrderService,
    ) -> None:
        self._session = session
        self._cart_repo = cart_repo
        self._products = product_service
        self._batch_repo = batch_repo
        self._order_service = order_service

    # ── CRUD ───────────────────────────────────────────────────

    async def add_item(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        qty: int,
    ) -> tuple[CartItemResponse, bool]:
        """加购：校验商品存在 → 查重累加或新建。

        Returns:
            (CartItemResponse, created): ``created=True`` 表示新建行；``False`` 表示累加。
        """
        # 校验商品存在（通过可购查询）
        products = await self._products.get_purchasable_products([str(product_id)])
        if not products:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Product {product_id} not found",
            )

        # 查重：已存在则累加数量
        existing = await self._cart_repo.get_by_user_and_product(
            user_id,
            product_id,
        )
        if existing is not None:
            existing.qty += qty
            await self._session.commit()
            await self._session.refresh(existing)
            return _to_cart_item_response(existing), False

        item = CartItem(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
            qty=qty,
        )
        await self._cart_repo.save(item)
        await self._session.commit()
        await self._session.refresh(item)
        return _to_cart_item_response(item), True

    async def update_qty(
        self,
        item: CartItem,
        qty: int,
    ) -> CartItemResponse:
        """修改数量：deps `get_current_cart_item` 已鉴权归属（非本人 404），仅更新 qty。"""
        item.qty = qty
        await self._session.commit()
        await self._session.refresh(item)
        return _to_cart_item_response(item)

    async def delete_item(
        self,
        item: CartItem,
    ) -> None:
        """删除行：deps `get_current_cart_item` 已鉴权归属（非本人 404），直接删除。"""
        await self._cart_repo.delete(item)
        await self._session.commit()

    # ── 列表 enrichment ────────────────────────────────────────

    async def list_cart(self, user_id: uuid.UUID) -> CartListResponse:
        """GET /cart：批量 enrichment → 按店分组 + invalid_items。"""
        cart_items = await self._cart_repo.list_by_user_id(user_id)

        if not cart_items:
            return CartListResponse(shops=[], invalid_items=[])

        # 批量查询商品信息（一次 SQL，避免 N+1）
        product_ids = [str(item.product_id) for item in cart_items]
        products = await self._products.get_purchasable_products(product_ids)
        product_map: dict[str, PurchasableProduct] = {p.id: p for p in products}

        # 按 shop_id 分组
        shops_map: dict[str, list[CartShopItem]] = {}
        invalid_items: list[CartInvalidItem] = []

        for item in cart_items:
            pid = str(item.product_id)
            product = product_map.get(pid)

            if product is None:
                invalid_items.append(
                    CartInvalidItem(
                        cart_item_id=str(item.id),
                        product_id=pid,
                        reason="not_found",
                    )
                )
            elif not product.is_published:
                invalid_items.append(
                    CartInvalidItem(
                        cart_item_id=str(item.id),
                        product_id=pid,
                        reason="product_unpublished",
                    )
                )
            elif not product.shop_active:
                invalid_items.append(
                    CartInvalidItem(
                        cart_item_id=str(item.id),
                        product_id=pid,
                        reason="shop_closed",
                    )
                )
            else:
                shop_id = product.shop_id
                if shop_id not in shops_map:
                    shops_map[shop_id] = []
                shops_map[shop_id].append(
                    CartShopItem(
                        cart_item_id=str(item.id),
                        product_id=pid,
                        product_name=product.name,
                        unit_price=product.price,
                        qty=item.qty,
                    )
                )

        # 构建 shops 数组：shop_name 从 PurchasableProduct 获取
        shops: list[CartShopGroup] = []
        for sid, items in shops_map.items():
            first_pid = items[0].product_id
            shop_name = product_map[first_pid].shop_name
            shops.append(
                CartShopGroup(
                    shop_id=sid,
                    shop_name=shop_name,
                    items=items,
                )
            )

        return CartListResponse(shops=shops, invalid_items=invalid_items)

    # ── Checkout 编排 ────────────────────────────────────────────

    async def checkout(
        self,
        user_id: uuid.UUID,
        cart_item_ids: list[uuid.UUID],
    ) -> CheckoutResponse:
        """结算：单事务内创建 batch + N 个子订单 + 删 cart 行。

        编排入口，唯一 commit 在此方法的末尾。
        """
        if not cart_item_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="cart_item_ids must not be empty",
            )

        # 1. 加载 cart items，校验归属
        cart_items: list[CartItem] = []
        for cid in cart_item_ids:
            item = await self._cart_repo.get_by_id(cid)
            if item is None or str(item.user_id) != str(user_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Cart item {cid} not found or not owned by user",
                )
            cart_items.append(item)

        # 2. 批量查询商品信息
        product_ids = [str(item.product_id) for item in cart_items]
        products = await self._products.get_purchasable_products(product_ids)
        product_map: dict[str, PurchasableProduct] = {p.id: p for p in products}

        # 3. 校验每个商品可购、库存充足
        items_by_shop: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for item in cart_items:
            pid = str(item.product_id)
            product = product_map.get(pid)
            if product is None or not product.is_published or not product.shop_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Product {pid} is not purchasable",
                )
            if product.stock < item.qty:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Insufficient stock for product {pid}",
                )
            # 校验自购
            if str(user_id) == product.owner_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Buyer cannot purchase from their own shop",
                )
            items_by_shop[product.shop_id].append((pid, item.qty))

        # 4. 创建 checkout_batch
        batch = CheckoutBatch(
            id=uuid.uuid4(),
            buyer_user_id=user_id,
        )
        await self._batch_repo.save(batch)
        await self._session.flush()

        # 5. 按店建单（commit=False，由本方法统一提交）
        created_orders: list = []
        try:
            for shop_id, shop_items in items_by_shop.items():
                order = await self._order_service.create_order_core(
                    user_id,
                    shop_items,
                    initiated_by="buyer",
                    expected_shop_id=uuid.UUID(shop_id),
                    commit=False,
                    checkout_batch_id=batch.id,
                )
                created_orders.append(order)
        except HTTPException:
            await self._session.rollback()
            raise

        # 6. 删除已结算 cart 行
        await self._cart_repo.delete_batch(cart_item_ids)

        # 7. 构建响应数据（在 commit 前收集，避免 commit 后 ORM 过期）
        # 复用 OrderService 的模块级映射，避免与 service.py `to_order_response` 双份维护
        order_responses = [to_order_response(o) for o in created_orders]

        response = CheckoutResponse(
            checkout_batch_id=str(batch.id),
            orders=order_responses,
        )

        # 8. 唯一 commit
        await self._session.commit()

        return response

    async def get_checkout_batch(
        self,
        batch: CheckoutBatch,
    ) -> CheckoutBatchResponse:
        """查看结算批次详情：子订单（懒释放+items）→ 聚合 → 派生状态 → build schema。

        deps `get_current_checkout_batch` 已做买家鉴权（非本人 404，design Decision 4c）；
        schema 由 service 产出。
        子订单数据经 OrderService.list_orders_by_checkout_batch（方案 A：order 数据访问留在 OrderService）。
        """
        orders = await self._order_service.list_orders_by_checkout_batch(batch.id)

        paid_total = Decimal("0.00")
        remaining_total = Decimal("0.00")
        statuses: set[str] = set()
        shops_map: dict[str, list[CheckoutBatchOrder]] = {}

        for order in orders:
            statuses.add(order.status)

            item_responses = [
                CheckoutBatchOrderItem(
                    id=str(i.id),
                    product_id=str(i.product_id),
                    product_name=i.product_name,
                    unit_price=str(i.unit_price),
                    qty=i.qty,
                )
                for i in order.items
            ]

            order_data = CheckoutBatchOrder(
                id=str(order.id),
                shop_id=str(order.shop_id),
                status=order.status,
                initiated_by=order.initiated_by,
                total_amount=str(order.total_amount),
                expires_at=order.expires_at,
                items=item_responses,
                created_at=order.created_at,
            )

            sid = str(order.shop_id)
            if sid not in shops_map:
                shops_map[sid] = []
            shops_map[sid].append(order_data)

            if order.status == "awaiting_payment":
                remaining_total += order.total_amount
            elif order.status == "confirmed":
                paid_total += order.total_amount

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
