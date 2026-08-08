"""ordering 域 cart 业务逻辑：CRUD + 列表 enrichment + checkout 编排。"""

import uuid
from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import PurchasableProduct
from app.catalog.service import ShopService
from app.ordering.cart_repository import CartRepository
from app.ordering.checkout_batch_repository import CheckoutBatchRepository
from app.ordering.models import CartItem, CheckoutBatch
from app.ordering.schemas import (
    CartInvalidItem,
    CartListResponse,
    CartShopGroup,
    CartShopItem,
    CheckoutResponse,
)
from app.ordering.service import OrderService


class CartService:
    """购物车业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
        cart_repo: CartRepository,
        catalog_service: ShopService,
        batch_repo: CheckoutBatchRepository,
        order_service: OrderService,
    ) -> None:
        self._session = session
        self._cart_repo = cart_repo
        self._catalog = catalog_service
        self._batch_repo = batch_repo
        self._order_service = order_service

    # ── CRUD ───────────────────────────────────────────────────

    async def add_item(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        qty: int,
    ) -> tuple[CartItem, bool]:
        """加购：校验商品存在 → 查重累加或新建。

        Returns:
            (CartItem, created): ``created=True`` 表示新建行；``False`` 表示累加。
        """
        # 校验商品存在（通过可购查询）
        products = await self._catalog.get_purchasable_products([str(product_id)])
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
            return existing, False

        item = CartItem(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
            qty=qty,
        )
        await self._cart_repo.save(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item, True

    async def update_qty(
        self,
        user_id: uuid.UUID,
        cart_item_id: uuid.UUID,
        qty: int,
    ) -> CartItem:
        """修改数量：须属当前用户 → 更新 qty。"""
        item = await self._cart_repo.get_by_id(cart_item_id)
        if item is None or str(item.user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cart item not found",
            )
        item.qty = qty
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def delete_item(
        self,
        user_id: uuid.UUID,
        cart_item_id: uuid.UUID,
    ) -> None:
        """删除行：须属当前用户 → 删除。"""
        item = await self._cart_repo.get_by_id(cart_item_id)
        if item is None or str(item.user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cart item not found",
            )
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
        products = await self._catalog.get_purchasable_products(product_ids)
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
        products = await self._catalog.get_purchasable_products(product_ids)
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
                order = await self._order_service._create_order_core(
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
        from app.ordering.schemas import OrderResponse

        order_responses: list[OrderResponse] = []
        for o in created_orders:
            items_data = [
                {
                    "id": str(i.id),
                    "product_id": str(i.product_id),
                    "product_name": i.product_name,
                    "unit_price": str(i.unit_price),
                    "qty": i.qty,
                }
                for i in o.items
            ]
            order_responses.append(
                OrderResponse(
                    id=str(o.id),
                    buyer_user_id=str(o.buyer_user_id),
                    shop_id=str(o.shop_id),
                    initiated_by=o.initiated_by,  # type: ignore[arg-type]
                    status=o.status,  # type: ignore[arg-type]
                    cancel_reason=o.cancel_reason,
                    checkout_batch_id=str(o.checkout_batch_id)
                    if o.checkout_batch_id
                    else None,
                    total_amount=str(o.total_amount),
                    expires_at=o.expires_at,
                    items=items_data,
                    created_at=o.created_at,
                    updated_at=o.updated_at,
                )
            )

        response = CheckoutResponse(
            checkout_batch_id=str(batch.id),
            orders=order_responses,
        )

        # 8. 唯一 commit
        await self._session.commit()

        return response
