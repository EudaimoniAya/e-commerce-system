"""ordering 域业务逻辑：建单、支付桩、发货、确认收货、取消、列表、懒释放。"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import PurchasableProduct
from app.catalog.service import ShopService
from app.infra.config import get_settings
from app.ordering.models import Order, OrderItem
from app.ordering.repository import OrderItemRepository, OrderRepository

_NOT_FOUND_MSG = "Order not found"
_SELF_PURCHASE_MSG = "Buyer cannot purchase from their own shop"
_CROSS_SHOP_MSG = "All items must belong to the same shop"
_INVALID_STATE_MSG = "Order status does not allow this operation"
_EXPIRED_MSG = "Order has expired"


def _to_items_list(
    items: list[tuple[str, int]],
) -> list[dict]:
    """将路由层解析后的 (product_id, qty) 转为统一格式。"""
    return [{"product_id": pid, "qty": qty} for pid, qty in items]


class OrderService:
    """ordering 域编排服务（依赖 catalog 侧 service 与 ordering 侧仓储）。"""

    def __init__(
        self,
        session: AsyncSession,
        catalog_service: ShopService,
        order_repo: OrderRepository,
        item_repo: OrderItemRepository,
    ) -> None:
        self._session = session
        self._catalog = catalog_service
        self._order_repo = order_repo
        self._item_repo = item_repo

    # ── 懒释放 ──────────────────────────────────────────────

    async def expire_if_needed(self, order: Order) -> bool:
        """若订单 awaiting_payment 且已过期，终态化为 cancelled 并释放库存。

        返回 True 表示刚刚过期释放，False 表示无需处理。
        """
        if order.status != "awaiting_payment":
            return False
        if order.expires_at.tzinfo is None:
            expires_at = order.expires_at.replace(tzinfo=UTC)
        else:
            expires_at = order.expires_at

        if datetime.now(UTC) < expires_at:
            return False

        updated = await self._order_repo.update_status(
            order.id,
            from_statuses={"awaiting_payment"},
            to_status="cancelled",
            cancel_reason="expired",
        )
        if not updated:
            return False  # 并发丢失，别人先抢了

        items = await self._item_repo.list_by_order_id(order.id)
        release_items = [
            (str(item.product_id), item.qty) for item in items
        ]
        await self._catalog.release_stock(release_items)
        # 立即提交：可能由 deps（读路径）触发，不依赖调用方 commit
        await self._session.commit()
        return True

    # ── 创建 ────────────────────────────────────────────────

    async def create_order(
        self,
        buyer_user_id: uuid.UUID,
        items: list[tuple[str, int]],
    ) -> Order:
        """校验 → 预留库存 → 建单（同一事务）。

        返回持久化后的 Order（含 items）。
        失败抛出 HTTPException（422/403）。
        """
        item_dicts = _to_items_list(items)
        product_ids = [d["product_id"] for d in item_dicts]

        # 1. 查询可购商品
        products = await self._catalog.get_purchasable_products(product_ids)
        product_map: dict[str, PurchasableProduct] = {p.id: p for p in products}

        # 2. 校验每个商品存在且可购
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map.get(pid)
            if product is None or not product.is_published or not product.shop_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Product {pid} is not purchasable",
                )

        # 3. 校验同店
        shop_ids = {p.shop_id for p in product_map.values()}
        if len(shop_ids) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CROSS_SHOP_MSG,
            )
        shop_id = shop_ids.pop()

        # 4. 校验自购
        owner_id = list(product_map.values())[0].owner_user_id
        if str(buyer_user_id) == owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_SELF_PURCHASE_MSG,
            )

        # 5. 校验库存充足（get_purchasable_products 已返回实时 stock）
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map[pid]
            if product.stock < d["qty"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Insufficient stock for product {pid}",
                )

        # 6. 预留库存（条件更新，失败 → 422）
        reserve_items = [(d["product_id"], d["qty"]) for d in item_dicts]
        await self._catalog.reserve_stock(reserve_items)

        # 7. 计算 total_amount
        total = Decimal("0.00")
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map[pid]
            total += Decimal(product.price) * d["qty"]

        # 8. 创建订单
        settings = get_settings()
        now = datetime.now(UTC)
        order = Order(
            id=uuid.uuid4(),
            buyer_user_id=buyer_user_id,
            shop_id=uuid.UUID(shop_id),
            total_amount=total,
            expires_at=now
            + timedelta(seconds=settings.order_reservation_ttl_seconds),
        )
        await self._order_repo.save(order)
        # flush 以获取 order.id（供 OrderItem 外键使用）
        await self._session.flush()

        # 9. 创建订单行
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map[pid]
            item = OrderItem(
                order_id=order.id,
                product_id=uuid.UUID(pid),
                product_name=product.name,
                unit_price=Decimal(product.price),
                qty=d["qty"],
            )
            await self._item_repo.save(item)

        await self._session.commit()
        await self._session.refresh(order)
        # 加载 items 关系（expire_on_commit=False 下仍需要）
        order.items = await self._item_repo.list_by_order_id(order.id)
        return order

    # ── 支付桩 ──────────────────────────────────────────────

    async def pay_order(self, order: Order) -> Order:
        """支付桩：检查过期（409）→ 条件迁移到 confirmed。

        返回刷新后的订单。
        """
        expired = await self.expire_if_needed(order)
        if expired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_EXPIRED_MSG,
            )

        updated = await self._order_repo.update_status(
            order.id,
            from_statuses={"awaiting_payment"},
            to_status="confirmed",
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_INVALID_STATE_MSG,
            )

        await self._session.commit()
        await self._session.refresh(order)
        order.items = await self._item_repo.list_by_order_id(order.id)
        return order

    # ── 发货 ────────────────────────────────────────────────

    async def create_shipment(
        self, order: Order, note: str | None = None,
    ) -> Order:
        """卖家发货：条件迁移 confirmed → shipped。"""
        updated = await self._order_repo.update_status(
            order.id,
            from_statuses={"confirmed"},
            to_status="shipped",
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_INVALID_STATE_MSG,
            )

        if note is not None:
            order.note = note

        await self._session.commit()
        await self._session.refresh(order)
        order.items = await self._item_repo.list_by_order_id(order.id)
        return order

    # ── 确认收货 ────────────────────────────────────────────

    async def confirm_receipt(self, order: Order) -> Order:
        """买家确认收货：条件迁移 shipped → completed。"""
        updated = await self._order_repo.update_status(
            order.id,
            from_statuses={"shipped"},
            to_status="completed",
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_INVALID_STATE_MSG,
            )

        await self._session.commit()
        await self._session.refresh(order)
        order.items = await self._item_repo.list_by_order_id(order.id)
        return order

    # ── 取消 ────────────────────────────────────────────────

    async def cancel_order(
        self, order: Order, cancel_reason: str,
    ) -> Order:
        """取消订单（买家/卖家）：条件迁移 → cancelled + 释放库存。"""
        updated = await self._order_repo.update_status(
            order.id,
            from_statuses={"awaiting_payment", "confirmed", "shipped"},
            to_status="cancelled",
            cancel_reason=cancel_reason,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_INVALID_STATE_MSG,
            )

        items = await self._item_repo.list_by_order_id(order.id)
        release_items = [
            (str(item.product_id), item.qty) for item in items
        ]
        await self._catalog.release_stock(release_items)

        await self._session.commit()
        await self._session.refresh(order)
        order.items = items
        return order

    # ── 列表 ────────────────────────────────────────────────

    async def list_buyer_orders(
        self,
        buyer_user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        """买家订单列表。"""
        orders, total = await self._order_repo.list_by_buyer(
            buyer_user_id, limit=limit, offset=offset,
        )
        for order in orders:
            order.items = await self._item_repo.list_by_order_id(order.id)
        return orders, total

    async def list_shop_orders(
        self,
        shop_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        """店铺订单列表（店主查看本店订单）。"""
        orders, total = await self._order_repo.list_by_shop(
            shop_id, limit=limit, offset=offset,
        )
        for order in orders:
            order.items = await self._item_repo.list_by_order_id(order.id)
        return orders, total

    async def get_order_or_404(
        self, order_id: uuid.UUID,
    ) -> Order:
        """按 ID 查询订单，不存在时 404。"""
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_NOT_FOUND_MSG,
            )
        order.items = await self._item_repo.list_by_order_id(order.id)
        return order
