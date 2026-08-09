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
from app.ordering.schemas import BatchPayResponse, OrderResponse, PaginatedOrders
from app.user.service import UserService

_NOT_FOUND_MSG = "Order not found"
_SELF_PURCHASE_MSG = "Buyer cannot purchase from their own shop"
_CROSS_SHOP_MSG = "All items must belong to the same shop"
_INVALID_STATE_MSG = "Order status does not allow this operation"
_EXPIRED_MSG = "Order has expired"


def _get_reservation_ttl() -> int:
    """读取订单预留 TTL（秒）。"""
    return get_settings().order_reservation_ttl_seconds


def _to_items_list(
    items: list[tuple[str, int]],
) -> list[dict]:
    """将路由层解析后的 (product_id, qty) 转为统一格式。"""
    return [{"product_id": pid, "qty": qty} for pid, qty in items]


def _to_order_response(order: Order) -> OrderResponse:
    """ORM Order → OrderResponse（含 items）。

    模块级私有映射（与 catalog / user / engagement / support 各域 `_to_*` 一致）；
    ordering 域内 service 与 deps 均可调用，router 不做 ORM 映射。
    """
    return OrderResponse(
        id=str(order.id),
        buyer_user_id=str(order.buyer_user_id),
        shop_id=str(order.shop_id),
        initiated_by=order.initiated_by,  # type: ignore[arg-type]
        status=order.status,  # type: ignore[arg-type]
        cancel_reason=order.cancel_reason,
        checkout_batch_id=str(order.checkout_batch_id)
        if order.checkout_batch_id
        else None,
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


class OrderService:
    """ordering 域编排服务（依赖 catalog 侧 service、user 侧 service 与 ordering 侧仓储）。"""

    def __init__(
        self,
        session: AsyncSession,
        catalog_service: ShopService,
        order_repo: OrderRepository,
        item_repo: OrderItemRepository,
        user_service: UserService,
    ) -> None:
        self._session = session
        self._catalog = catalog_service
        self._order_repo = order_repo
        self._item_repo = item_repo
        self._user_service = user_service

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
        release_items = [(str(item.product_id), item.qty) for item in items]
        await self._catalog.release_stock(release_items)
        # 立即提交：可能由 deps（读路径）触发，不依赖调用方 commit
        await self._session.commit()
        # 刷新 ORM，避免 commit 后访问 updated_at 等字段触发 sync 懒加载（MissingGreenlet）
        await self._session.refresh(order)
        return True

    # ── 创建（内核） ────────────────────────────────────────

    async def _create_order_core(
        self,
        buyer_user_id: uuid.UUID,
        items: list[tuple[str, int]],
        *,
        initiated_by: str = "buyer",
        expected_shop_id: uuid.UUID | None = None,
        commit: bool = True,
        checkout_batch_id: uuid.UUID | None = None,
    ) -> Order:
        """建单内核：校验商品可购/库存 → 预留 → 建单。

        - buyer 路径：expected_shop_id=None，shop_id 由商品推导
        - seller 路径：expected_shop_id=卖家店铺，所有商品必须归属该店
        自购校验由内核统一处理（owner_id 从商品推导）。
        买家存在/active 校验由调用方负责。

        Args:
            commit: True（默认）时末尾 commit + refresh（立即购买/卖家建单）；
                    False 时仅 flush，由调用方（CartService.checkout）统一 commit。
            checkout_batch_id: 通过 cart checkout 建单时传入的 batch ID；
                               None 表示立即购买/卖家建单。
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

        # 3. 校验同店 / 归属指定店铺
        if expected_shop_id is not None:
            for d in item_dicts:
                pid = d["product_id"]
                product = product_map[pid]
                if uuid.UUID(product.shop_id) != expected_shop_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Product {pid} does not belong to this shop",
                    )
            shop_id = expected_shop_id
        else:
            shop_ids = {p.shop_id for p in product_map.values()}
            if len(shop_ids) != 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_CROSS_SHOP_MSG,
                )
            shop_id = uuid.UUID(shop_ids.pop())

        # 4. 校验自购
        owner_id = list(product_map.values())[0].owner_user_id
        if str(buyer_user_id) == owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_SELF_PURCHASE_MSG,
            )

        # 5. 校验库存
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map[pid]
            if product.stock < d["qty"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Insufficient stock for product {pid}",
                )

        # 6. 预留库存
        reserve_items = [(d["product_id"], d["qty"]) for d in item_dicts]
        await self._catalog.reserve_stock(reserve_items)

        # 7. 计算 total_amount
        total = Decimal("0.00")
        for d in item_dicts:
            pid = d["product_id"]
            product = product_map[pid]
            total += Decimal(product.price) * d["qty"]

        # 8. 创建订单
        now = datetime.now(UTC)
        order = Order(
            id=uuid.uuid4(),
            buyer_user_id=buyer_user_id,
            shop_id=shop_id,
            total_amount=total,
            expires_at=now + timedelta(seconds=_get_reservation_ttl()),
            initiated_by=initiated_by,
            checkout_batch_id=checkout_batch_id,
        )
        await self._order_repo.save(order)
        await self._session.flush()

        # 9. 创建订单行
        created_items: list[OrderItem] = []
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
            created_items.append(item)

        if commit:
            await self._session.commit()
            await self._session.refresh(order)
            order.items = await self._item_repo.list_by_order_id(order.id)
        else:
            await self._session.flush()
            # refresh 以填充 server_default 列（created_at/updated_at），
            # 避免 CartService 后续访问时触发 MissingGreenlet
            await self._session.refresh(order)
            for item in created_items:
                await self._session.refresh(item)
            order.items = created_items

        return order

    # ── 买家建单 ────────────────────────────────────────────

    async def create_order(
        self,
        buyer_user_id: uuid.UUID,
        items: list[tuple[str, int]],
    ) -> OrderResponse:
        """买家建单：委托内核（initiated_by=buyer，shop 由商品推导）。"""
        order = await self._create_order_core(
            buyer_user_id,
            items,
            initiated_by="buyer",
        )
        return _to_order_response(order)

    # ── 卖家建单 ────────────────────────────────────────────

    async def create_order_by_seller(
        self,
        owner_user_id: uuid.UUID,
        buyer_user_id: uuid.UUID,
        items: list[tuple[str, int]],
    ) -> OrderResponse:
        """卖家为指定买家建单：解析本店 → 校验商品归属 → 买家存在 → 建单。

        店铺归属由本方法经 catalog 解析（router 不再编排）。
        本方法校验：买家存在且 active、非自购、所有商品属本店 → 建单。
        校验顺序：店铺解析 → 商品归属/可购 → 自购 → 买家存在 → 内核（库存+建单）。
        """
        shop = await self._catalog.get_my_shop(owner_user_id)
        seller_shop_id = uuid.UUID(shop.id)
        item_dicts = _to_items_list(items)
        product_ids = [d["product_id"] for d in item_dicts]

        # 先做只读校验：商品可购、归属指定店铺（不涉及写操作）
        products = await self._catalog.get_purchasable_products(product_ids)
        product_map: dict[str, PurchasableProduct] = {p.id: p for p in products}

        for d in item_dicts:
            pid = d["product_id"]
            product = product_map.get(pid)
            if product is None or not product.is_published or not product.shop_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Product {pid} is not purchasable",
                )
            if uuid.UUID(product.shop_id) != seller_shop_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Product {pid} does not belong to this shop",
                )

        # 校验自购
        owner_id = list(product_map.values())[0].owner_user_id
        if str(buyer_user_id) == owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_SELF_PURCHASE_MSG,
            )

        # 校验买家存在且 active（不存在→404，禁用→422）
        await self._user_service.get_user_summary(str(buyer_user_id))

        order = await self._create_order_core(
            buyer_user_id,
            items,
            initiated_by="seller",
            expected_shop_id=seller_shop_id,
        )
        return _to_order_response(order)

    # ── 支付桩 ──────────────────────────────────────────────

    async def pay_order(self, user_id: uuid.UUID, order: Order) -> OrderResponse:
        """支付桩：非买家 403 → 检查过期（409）→ 条件迁移到 confirmed。

        buyer 校验由本方法负责（router 只传 user_id）。
        """
        if str(order.buyer_user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the buyer can pay for this order",
            )

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
        return _to_order_response(order)

    # ── 发货 ────────────────────────────────────────────────

    async def create_shipment(
        self,
        user_id: uuid.UUID,
        order: Order,
        note: str | None = None,
    ) -> OrderResponse:
        """卖家发货：校验本店归属（403）→ 条件迁移 confirmed → shipped。

        店铺归属由本方法经 catalog 解析（router 不再编排）。
        """
        try:
            shop = await self._catalog.get_my_shop(user_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not your shop's order",
            ) from None
        if str(order.shop_id) != str(shop.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not your shop's order",
            )

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
        return _to_order_response(order)

    # ── 确认收货 ────────────────────────────────────────────

    async def confirm_receipt(self, order: Order) -> OrderResponse:
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
        return _to_order_response(order)

    # ── 取消 ────────────────────────────────────────────────

    async def cancel_order(
        self,
        user_id: uuid.UUID,
        order: Order,
    ) -> OrderResponse:
        """取消订单（买家/卖家）：条件迁移 → cancelled + 释放库存。

        cancel_reason 由本方法按角色选择（router 只传 user_id）。
        """
        is_buyer = str(order.buyer_user_id) == str(user_id)
        cancel_reason = "buyer_cancelled" if is_buyer else "seller_cancelled"
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
        release_items = [(str(item.product_id), item.qty) for item in items]
        await self._catalog.release_stock(release_items)

        await self._session.commit()
        await self._session.refresh(order)
        order.items = items
        return _to_order_response(order)

    # ── 列表 ────────────────────────────────────────────────

    async def list_buyer_orders(
        self,
        buyer_user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedOrders:
        """买家订单列表。"""
        orders, total = await self._order_repo.list_by_buyer(
            buyer_user_id,
            limit=limit,
            offset=offset,
        )
        items: list[OrderResponse] = []
        for order in orders:
            await self.expire_if_needed(order)
            order.items = await self._item_repo.list_by_order_id(order.id)
            items.append(_to_order_response(order))
        return PaginatedOrders(items=items, total=total, limit=limit, offset=offset)

    async def list_shop_orders(
        self,
        owner_user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedOrders:
        """店铺订单列表（店主查看本店订单）：先解析本店，再分页查订单。"""
        shop = await self._catalog.get_my_shop(owner_user_id)
        shop_id = uuid.UUID(shop.id)
        orders, total = await self._order_repo.list_by_shop(
            shop_id,
            limit=limit,
            offset=offset,
        )
        items: list[OrderResponse] = []
        for order in orders:
            await self.expire_if_needed(order)
            order.items = await self._item_repo.list_by_order_id(order.id)
            items.append(_to_order_response(order))
        return PaginatedOrders(items=items, total=total, limit=limit, offset=offset)

    async def get_order_or_404(
        self,
        order_id: uuid.UUID,
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

    async def get_order_response(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OrderResponse:
        """买家或本店店主查看订单详情：fetch → 404 → 懒释放 → 鉴权 → 映射。

        读路径 schema 唯一出口；router 只传 order_id + user_id。
        鉴权语义与 deps `get_order_for_buyer_or_shop` 一致：非买家且非本店店主 → 404。
        """
        order = await self.get_order_or_404(order_id)

        # 懒释放（expire_if_needed 内部会 commit 过期变更）
        expired = await self.expire_if_needed(order)
        if expired:
            order = await self.get_order_or_404(order_id)

        # 买家或本店店主，否则 404
        if str(order.buyer_user_id) != str(user_id):
            try:
                shop = await self._catalog.get_my_shop(user_id)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=_NOT_FOUND_MSG,
                ) from None
            if str(shop.id) != str(order.shop_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=_NOT_FOUND_MSG,
                )

        return _to_order_response(order)

    # ── 批量支付 ──────────────────────────────────────────────

    async def batch_pay_orders(
        self,
        user_id: uuid.UUID,
        order_ids: list[uuid.UUID],
    ) -> BatchPayResponse:
        """批量支付桩：全有或全无，单事务。

        1. 校验全部 order 存在且属当前用户
        2. 对全部执行 expire_if_needed
        3. 校验全部为 awaiting_payment（任一不满足 → 409）
        4. 批量条件更新 → confirmed
        5. commit
        """
        if not order_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="order_ids must not be empty",
            )

        # 1. 加载全部订单，校验归属
        orders: list[Order] = []
        for oid in order_ids:
            order = await self._order_repo.get_by_id(oid)
            if order is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=_NOT_FOUND_MSG,
                )
            if str(order.buyer_user_id) != str(user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not allowed to pay this order",
                )
            orders.append(order)

        # 2. 对全部执行懒释放
        for order in orders:
            await self.expire_if_needed(order)

        # 3. 重新加载，校验全部 awaiting_payment
        for order in orders:
            refreshed = await self._order_repo.get_by_id(order.id)
            if refreshed is None or refreshed.status != "awaiting_payment":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=_INVALID_STATE_MSG,
                )

        # 4. 批量条件更新
        updated = await self._order_repo.batch_update_status(
            order_ids,
            from_statuses={"awaiting_payment"},
            to_status="confirmed",
        )
        if updated != len(order_ids):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_INVALID_STATE_MSG,
            )

        await self._session.commit()

        # 5. 刷新并加载 items
        result: list[Order] = []
        for order in orders:
            await self._session.refresh(order)
            order.items = await self._item_repo.list_by_order_id(order.id)
            result.append(order)

        return BatchPayResponse(orders=[_to_order_response(o) for o in result])
