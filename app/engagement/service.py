"""engagement 域业务逻辑：收藏 CRUD + 浏览 upsert/列表/删除。"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import EngagementProduct
from app.catalog.service import ShopService
from app.engagement.models import UserBrowseHistory, UserFavorite
from app.engagement.repository import BrowseRepository, FavoriteRepository
from app.engagement.schemas import (
    BrowseItem,
    BrowseListResponse,
    FavoriteItem,
    FavoriteListResponse,
    UnavailableBrowseItem,
    UnavailableFavoriteItem,
)
from app.infra.config import get_settings


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


# ── 浏览（user_browse_history）────────────────────────────────


def _to_browse_item(row: UserBrowseHistory) -> BrowseItem:
    """ORM UserBrowseHistory → BrowseItem（仅浏览元数据，不含 product 详情）。"""
    return BrowseItem(
        id=str(row.id),
        product_id=str(row.product_id),
        first_viewed_at=row.first_viewed_at,
        last_viewed_at=row.last_viewed_at,
        view_count=row.view_count,
    )


def _to_unavailable_browse_item(
    row: UserBrowseHistory,
    reason: Literal["not_found", "product_unpublished", "shop_closed"],
    product_name: str | None,
    image_url: str | None,
) -> UnavailableBrowseItem:
    """ORM UserBrowseHistory + enrichment 字段 → UnavailableBrowseItem。"""
    return UnavailableBrowseItem(
        id=str(row.id),
        product_id=str(row.product_id),
        first_viewed_at=row.first_viewed_at,
        last_viewed_at=row.last_viewed_at,
        view_count=row.view_count,
        reason=reason,
        product_name=product_name,
        image_url=image_url,
    )


class BrowseService:
    """浏览业务服务（POST 校验 + 异步 upsert、分页列表、单删）。

    ``record_browse_async`` 作为 BackgroundTask 在响应后运行；FastAPI 0.139 中
    dependency teardown 晚于后台任务，故可安全复用请求级 ``self._session``
    （测试经 SAVEPOINT override 与 db_session 同事务，写入对断言可见）。
    """

    def __init__(
        self,
        session: AsyncSession,
        browse_repo: BrowseRepository,
        catalog_service: ShopService,
    ) -> None:
        self._session = session
        self._browse_repo = browse_repo
        self._catalog = catalog_service

    # ── POST /browse ───────────────────────────────────────────

    async def record_browse(
        self,
        user_id: uuid.UUID,
        product_id: str,
        background_tasks: BackgroundTasks,
    ) -> None:
        """同步校验 + 调度后台 upsert。

        catalog 行存在即可记录（偏好 ≠ 可购，不要求上架/店 active）；
        catalog 无此商品 → 422 且不调度 BackgroundTask。
        """
        products = await self._catalog.get_products_for_engagement([product_id])
        if not products:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Product {product_id} not found",
            )
        background_tasks.add_task(
            self.record_browse_async,
            user_id=user_id,
            product_id=product_id,
        )

    async def record_browse_async(
        self,
        user_id: uuid.UUID,
        product_id: str,
    ) -> None:
        """BackgroundTask：upsert 浏览行（首次 INSERT / debounce / 间断重置 / 递增）。

        时间基准决策（naive vs aware，为何用 UTC 墙钟）：

        - 本方法的一切分支（debounce ≤5s、活跃递增、间断重置 >retention）都依赖
          ``gap = now - last_viewed_at``，必须用**一致的时间基准**比较。
        - MySQL ``DATETIME`` 列**不存时区**：落库即丢 tz，读回（raw SQL 与 ORM）
          必为 **naive**（无 tzinfo）。已实证。
        - 测试 seed（``tests/testkit/db/engagement.py::seed_browse_history``）用
          ``datetime.now(UTC)``（aware）直插，asyncmy 按 **UTC 墙钟 naive** 存储。
        - 故 ``now`` 必须取 ``datetime.now(UTC).replace(tzinfo=None)``（UTC 墙钟
          naive），才能与 DB / 测试对齐，``gap`` 相减正确。
        - 若误用 ``datetime.now()``（本地 CST+8），与 UTC 墙钟差 **8 小时**：
          2 秒间隔会被算成 8h → debounce 判定失效、view_count 被错误 +1。
          已探针实证：UTC-naive gap=0:00:01.978（正确）vs local gap=8:00:01.978（错误）。
        """
        settings = get_settings()
        debounce = timedelta(seconds=settings.browse_debounce_seconds)
        retention = timedelta(days=settings.browse_history_retention_days)
        now = datetime.now(UTC).replace(tzinfo=None)

        existing = await self._browse_repo.get_by_user_and_product(user_id, product_id)
        if existing is None:
            self._session.add(
                UserBrowseHistory(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    product_id=product_id,
                    first_viewed_at=now,
                    last_viewed_at=now,
                    view_count=1,
                )
            )
        else:
            gap = now - existing.last_viewed_at
            if gap <= debounce:
                # debounce 内重复 POST：仅刷新最近浏览时间，不 +1
                existing.last_viewed_at = now
            elif gap > retention:
                # 间断重置：距上次查看超 retention → view_count 归 1（first_viewed_at 不变）
                existing.last_viewed_at = now
                existing.view_count = 1
            else:
                # 活跃期间：debounce 已过且未超 retention → 累计 +1
                existing.last_viewed_at = now
                existing.view_count += 1
        await self._session.commit()

    # ── DELETE /browse/{product_id} ────────────────────────────

    async def delete_browse(
        self,
        user_id: uuid.UUID,
        product_id: str,
    ) -> None:
        """删除浏览记录：仅本人记录，否则 404（不暴露存在性）。"""
        row = await self._browse_repo.get_by_user_and_product(user_id, product_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Browse not found",
            )
        await self._browse_repo.delete(row)
        await self._session.commit()

    # ── GET /browse 列表 ───────────────────────────────────────

    async def list_browses(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> BrowseListResponse:
        """分页列表：批量 enrichment → items + unavailable_items。

        ``total`` 为该用户全部 browse 行数（含 unavailable），不受分页影响；
        本方法不删除 unavailable 行（由用户 DELETE 主动清理）。
        """
        rows, total = await self._browse_repo.list_page(
            user_id, limit=limit, offset=offset
        )

        if not rows:
            return BrowseListResponse(
                items=[],
                unavailable_items=[],
                total=total,
                limit=limit,
                offset=offset,
            )

        product_ids = [str(r.product_id) for r in rows]
        products = await self._catalog.get_products_for_engagement(product_ids)
        product_map: dict[str, EngagementProduct] = {p.id: p for p in products}

        items, unavailable = await self._classify_browses(rows, product_map)

        return BrowseListResponse(
            items=items,
            unavailable_items=unavailable,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def _classify_browses(
        self,
        rows: list[UserBrowseHistory],
        product_map: dict[str, EngagementProduct],
    ) -> tuple[list[BrowseItem], list[UnavailableBrowseItem]]:
        """分类单点：items（可展示）/ unavailable_items（失效）。GET 与未来消费方共用。"""
        items: list[BrowseItem] = []
        unavailable: list[UnavailableBrowseItem] = []

        for row in rows:
            pid = str(row.product_id)
            product = product_map.get(pid)
            if product is None:
                unavailable.append(
                    _to_unavailable_browse_item(row, "not_found", None, None)
                )
            elif not product.is_published:
                unavailable.append(
                    _to_unavailable_browse_item(
                        row, "product_unpublished", product.name, product.image_url
                    )
                )
            elif not product.shop_active:
                unavailable.append(
                    _to_unavailable_browse_item(
                        row, "shop_closed", product.name, product.image_url
                    )
                )
            else:
                items.append(_to_browse_item(row))

        return items, unavailable
