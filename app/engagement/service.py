"""engagement 域收藏业务逻辑：CRUD + 列表分类 + 批量删除。"""

import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import EngagementProduct
from app.catalog.service import ShopService
from app.engagement.models import UserFavorite
from app.engagement.repository import FavoriteRepository
from app.engagement.schemas import (
    FavoriteItem,
    FavoriteListResponse,
    UnavailableFavoriteItem,
)


def _to_favorite_item(favorite: UserFavorite) -> FavoriteItem:
    """ORM UserFavorite → FavoriteItem（仅 favorite 元数据，不含 product 详情）。"""
    return FavoriteItem(
        id=str(favorite.id),
        product_id=str(favorite.product_id),
        created_at=favorite.created_at,
    )


def _to_unavailable_item(
    favorite: UserFavorite,
    reason: Literal["not_found", "product_unpublished", "shop_closed"],
    product_name: str | None,
    image_url: str | None,
) -> UnavailableFavoriteItem:
    """ORM UserFavorite + enrichment 字段 → UnavailableFavoriteItem。"""
    return UnavailableFavoriteItem(
        id=str(favorite.id),
        product_id=str(favorite.product_id),
        created_at=favorite.created_at,
        reason=reason,
        product_name=product_name,
        image_url=image_url,
    )


class FavoriteService:
    """收藏业务服务（注入 catalog service 做跨域 enrichment/校验）。"""

    def __init__(
        self,
        session: AsyncSession,
        favorite_repo: FavoriteRepository,
        catalog_service: ShopService,
    ) -> None:
        self._session = session
        self._favorite_repo = favorite_repo
        self._catalog = catalog_service

    # ── POST /favorites ────────────────────────────────────────

    async def add_favorite(
        self,
        user_id: uuid.UUID,
        product_id: str,
    ) -> tuple[FavoriteItem, bool]:
        """收藏商品：catalog 行存在即可（偏好 ≠ 可购，不要求上架/店 active）。

        Returns:
            (favorite, created)：``created=True`` 新建（201）；``False`` 幂等返回既有（200）。
        """
        products = await self._catalog.get_products_for_engagement([product_id])
        if not products:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Product {product_id} not found",
            )

        existing = await self._favorite_repo.get_by_user_and_product(
            user_id, product_id
        )
        if existing is not None:
            return _to_favorite_item(existing), False

        favorite = UserFavorite(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
        )
        await self._favorite_repo.save(favorite)
        await self._session.commit()
        await self._session.refresh(favorite)
        return _to_favorite_item(favorite), True

    # ── DELETE /favorites/{product_id} ─────────────────────────

    async def delete_favorite(
        self,
        user_id: uuid.UUID,
        product_id: str,
    ) -> None:
        """取消收藏：仅本人收藏，否则 404（不暴露存在性）。"""
        favorite = await self._favorite_repo.get_by_user_and_product(
            user_id, product_id
        )
        if favorite is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Favorite not found",
            )
        await self._favorite_repo.delete(favorite)
        await self._session.commit()

    # ── GET /favorites 列表 ─────────────────────────────────────

    async def list_favorites(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> FavoriteListResponse:
        """分页列表：批量 enrichment → items + unavailable_items。

        ``total`` 为该用户全部 favorite 行数（含 unavailable），不受分页影响。
        """
        favorites, total = await self._favorite_repo.list_page(
            user_id, limit=limit, offset=offset
        )

        if not favorites:
            return FavoriteListResponse(
                items=[],
                unavailable_items=[],
                total=total,
                limit=limit,
                offset=offset,
            )

        # 批量查询商品（一次 SQL，避免 N+1）
        product_ids = [str(f.product_id) for f in favorites]
        products = await self._catalog.get_products_for_engagement(product_ids)
        product_map: dict[str, EngagementProduct] = {p.id: p for p in products}

        items, unavailable = await self._classify_favorites(favorites, product_map)

        return FavoriteListResponse(
            items=items,
            unavailable_items=unavailable,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def _classify_favorites(
        self,
        favorites: list[UserFavorite],
        product_map: dict[str, EngagementProduct],
    ) -> tuple[list[FavoriteItem], list[UnavailableFavoriteItem]]:
        """分类单点：items（可展示）/ unavailable_items（失效）。GET 与未来消费方共用。"""
        items: list[FavoriteItem] = []
        unavailable: list[UnavailableFavoriteItem] = []

        for favorite in favorites:
            pid = str(favorite.product_id)
            product = product_map.get(pid)
            if product is None:
                unavailable.append(
                    _to_unavailable_item(favorite, "not_found", None, None)
                )
            elif not product.is_published:
                unavailable.append(
                    _to_unavailable_item(
                        favorite, "product_unpublished", product.name, product.image_url
                    )
                )
            elif not product.shop_active:
                unavailable.append(
                    _to_unavailable_item(
                        favorite, "shop_closed", product.name, product.image_url
                    )
                )
            else:
                items.append(_to_favorite_item(favorite))

        return items, unavailable

    # ── POST /favorites/batch-delete ────────────────────────────

    async def batch_delete_favorites(
        self,
        user_id: uuid.UUID,
        product_ids: list[str],
    ) -> int:
        """批量删除收藏：单事务；未收藏 id 跳过；返回实际删除行数。

        ``product_ids`` 空列表由 router schema（min_length=1）先行 422 拦截。
        """
        deleted_count = await self._favorite_repo.delete_by_product_ids(
            user_id, product_ids
        )
        await self._session.commit()
        return deleted_count
