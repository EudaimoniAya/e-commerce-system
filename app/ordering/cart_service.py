"""ordering 域 cart 业务逻辑：CRUD + 列表 enrichment。"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import PurchasableProduct
from app.catalog.service import ShopService
from app.ordering.cart_repository import CartRepository
from app.ordering.models import CartItem
from app.ordering.schemas import (
    CartInvalidItem,
    CartListResponse,
    CartShopGroup,
    CartShopItem,
)


class CartService:
    """购物车业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
        cart_repo: CartRepository,
        catalog_service: ShopService,
    ) -> None:
        self._session = session
        self._cart_repo = cart_repo
        self._catalog = catalog_service

    # ── CRUD ───────────────────────────────────────────────────

    async def add_item(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        qty: int,
    ) -> CartItem:
        """加购：商品须存在 → 校验不重复 → 创建。"""
        # 校验商品存在（通过可购查询）
        products = await self._catalog.get_purchasable_products([str(product_id)])
        if not products:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Product {product_id} not found",
            )

        # 校验不重复
        existing = await self._cart_repo.get_by_user_and_product(
            user_id, product_id,
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Product already in cart; use PATCH to update quantity",
            )

        item = CartItem(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
            qty=qty,
        )
        await self._cart_repo.save(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

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
