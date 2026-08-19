"""catalog 域商品业务逻辑（ProductService）。"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog._media import resolve_single_url, resolve_urls_batch
from app.catalog.models import Product, Shop
from app.catalog.repository import CategoryRepository, ProductRepository
from app.catalog.schemas import (
    EngagementProduct,
    PaginatedProducts,
    ProductCategoryItem,
    ProductCreate,
    ProductRagSource,
    ProductResponse,
    ProductUpdate,
    PurchasableProduct,
)
from app.catalog.shop_service import ShopService
from app.media.service import MediaService

_PRODUCT_NOT_FOUND_MSG = "Product not found"
_SHOP_CLOSED_MSG = "Shop is closed"
_CATEGORY_NOT_FOUND_MSG = "One or more categories not found"
_PRODUCT_REF_INVALID_MSG = "Product ref not found or not in this shop"


def _format_price(price: Decimal) -> str:
    """将 DECIMAL 格式化为 API 价格字符串。"""
    return f"{price:.2f}"


def _to_product_response(
    product: Product,
    categories: list[ProductCategoryItem],
    image_url: str | None = None,
) -> ProductResponse:
    """ORM 商品转对外 DTO（image_url 由调用方经 media 域 resolve 后传入）。"""
    return ProductResponse(
        id=str(product.id),
        shop_id=str(product.shop_id),
        name=product.name,
        description=product.description,
        price=_format_price(product.price),
        stock=product.stock,
        is_published=product.is_published,
        image_url=image_url,
        categories=categories,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _parse_category_ids(category_ids: list[str]) -> list[uuid.UUID]:
    """将请求体中的类目 ID 转为 UUID 列表。"""
    return [uuid.UUID(item) for item in category_ids]


async def list_products_for_rag_indexing(
    shop_id: str | None = None,
    *,
    session: AsyncSession,
) -> list[ProductRagSource]:
    """跨域只读接口：供 ai 域索引拉取已上架商品文本语料（source_kind=catalog_text）。

    仅返回 ``is_published=True`` 的商品（可选按店过滤）；price 仅元数据传递、
    不进索引语料（design D2 语料边界）。ai 域经此接口取数，**不** import catalog ORM。
    """
    repository = ProductRepository(session)
    products = await repository.list_for_rag_indexing(
        shop_id=uuid.UUID(shop_id) if shop_id is not None else None
    )
    return [
        ProductRagSource(
            product_id=str(product.id),
            shop_id=str(product.shop_id),
            name=product.name,
            description=product.description,
            price=_format_price(product.price),
            is_published=product.is_published,
        )
        for product in products
    ]


class ProductService:
    """catalog 域商品业务服务（product + category repo + media）。

    承载商品 CRUD/列表、库存预留/释放、可购/engagement 跨域读、product ref 校验。
    """

    def __init__(
        self,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
        media_service: MediaService,
        shop_service: ShopService,
    ) -> None:
        self._product_repository = product_repository
        self._category_repository = category_repository
        self._media_service = media_service
        self._shop_service = shop_service

    async def _load_product_categories(
        self, product_id: uuid.UUID
    ) -> list[ProductCategoryItem]:
        """加载商品关联类目摘要。"""
        rows = await self._product_repository.get_category_items(product_id)
        return [
            ProductCategoryItem(id=cat_id, name=name, is_primary=is_primary)
            for cat_id, name, is_primary in rows
        ]

    async def _ensure_categories_exist(self, category_ids: list[uuid.UUID]) -> None:
        """校验类目 ID 均存在，否则 422。"""
        count = await self._category_repository.count_existing(category_ids)
        if count != len(category_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CATEGORY_NOT_FOUND_MSG,
            )

    def _ensure_shop_active(self, shop: Shop) -> None:
        """店铺 closed 时不允许写商品，返回 422。"""
        if shop.status == "closed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_SHOP_CLOSED_MSG,
            )

    async def create_product(self, shop: Shop, data: ProductCreate) -> ProductResponse:
        """店主在 active 店铺下创建商品。

        设置 ``primary_media_id`` 时经 media attach 校验（owner 403 / ``image/*`` 422），
        成功后同事务 ``mark_public``。
        """
        self._ensure_shop_active(shop)
        category_ids = _parse_category_ids(data.category_ids)
        primary_category_id = uuid.UUID(data.primary_category_id)
        await self._ensure_categories_exist(category_ids)

        if data.primary_media_id is not None:
            await self._media_service.assert_owned_by(
                data.primary_media_id, str(shop.owner_user_id)
            )
            await self._media_service.assert_image_content_type(data.primary_media_id)
            await self._media_service.mark_public(data.primary_media_id)

        product = await self._product_repository.create(
            product_id=uuid.uuid4(),
            shop_id=uuid.UUID(str(shop.id)),
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            is_published=data.is_published,
            primary_media_id=data.primary_media_id,
            category_ids=category_ids,
            primary_category_id=primary_category_id,
        )
        categories = await self._load_product_categories(uuid.UUID(str(product.id)))
        image_url = await resolve_single_url(
            self._media_service, product.primary_media_id
        )
        return _to_product_response(product, categories, image_url=image_url)

    async def update_product(
        self,
        product: Product,
        data: ProductUpdate,
    ) -> ProductResponse:
        """店主更新本店商品（``product`` 已由 ``get_current_product`` deps 鉴权解析）。

        店铺 closed 校验是状态依赖（Decision 4b 鉴权切分），归 service 方法内。
        """
        # 经 shop service 取本店上下文，避免 product → shop ORM 泄漏（design Risk 表）
        shop = await self._shop_service.get_shop_context(
            uuid.UUID(str(product.shop_id))
        )
        if shop.status == "closed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_SHOP_CLOSED_MSG,
            )

        if data.name is not None:
            product.name = data.name
        if data.description is not None:
            product.description = data.description
        if data.price is not None:
            product.price = data.price
        if data.stock is not None:
            product.stock = data.stock
        if data.is_published is not None:
            product.is_published = data.is_published

        # primary_media_id：显式 null 清空主图；设置时经 media attach 校验
        updates = data.model_dump(exclude_unset=True)
        if "primary_media_id" in updates:
            new_primary = updates["primary_media_id"]
            if new_primary is not None:
                await self._media_service.assert_owned_by(
                    new_primary, shop.owner_user_id
                )
                await self._media_service.assert_image_content_type(new_primary)
                await self._media_service.mark_public(new_primary)
            product.primary_media_id = new_primary

        if data.category_ids is not None:
            assert data.primary_category_id is not None
            category_ids = _parse_category_ids(data.category_ids)
            primary_category_id = uuid.UUID(data.primary_category_id)
            await self._ensure_categories_exist(category_ids)
            await self._product_repository.replace_categories(
                product.id,
                category_ids,
                primary_category_id,
            )

        updated = await self._product_repository.save(product)
        categories = await self._load_product_categories(product.id)
        image_url = await resolve_single_url(
            self._media_service, updated.primary_media_id
        )
        return _to_product_response(updated, categories, image_url=image_url)

    async def list_my_products(
        self,
        shop: Shop,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedProducts:
        """分页返回店主店铺全部商品。"""
        products, total = await self._product_repository.list_by_shop(
            uuid.UUID(str(shop.id)),
            limit=limit,
            offset=offset,
        )
        urls = await resolve_urls_batch(
            self._media_service, [p.primary_media_id for p in products]
        )
        items: list[ProductResponse] = []
        for product in products:
            categories = await self._load_product_categories(uuid.UUID(str(product.id)))
            image_url = (
                urls.get(str(product.primary_media_id))
                if product.primary_media_id is not None
                else None
            )
            items.append(_to_product_response(product, categories, image_url=image_url))
        return PaginatedProducts(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_public_products(
        self,
        *,
        category_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedProducts:
        """分页返回公开可见商品。"""
        products, total = await self._product_repository.list_public(
            category_id=category_id,
            limit=limit,
            offset=offset,
        )
        urls = await resolve_urls_batch(
            self._media_service, [p.primary_media_id for p in products]
        )
        items: list[ProductResponse] = []
        for product in products:
            categories = await self._load_product_categories(uuid.UUID(str(product.id)))
            image_url = (
                urls.get(str(product.primary_media_id))
                if product.primary_media_id is not None
                else None
            )
            items.append(_to_product_response(product, categories, image_url=image_url))
        return PaginatedProducts(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_public_product(self, product_id: uuid.UUID) -> ProductResponse:
        """公开查询已上架且店铺 active 的商品详情。"""
        product = await self._product_repository.get_public_by_id(product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_PRODUCT_NOT_FOUND_MSG,
            )
        categories = await self._load_product_categories(product_id)
        image_url = await resolve_single_url(
            self._media_service, product.primary_media_id
        )
        return _to_product_response(product, categories, image_url=image_url)

    async def get_purchasable_products(
        self, product_ids: list[str]
    ) -> list[PurchasableProduct]:
        """批量查询可购商品信息（供 ordering 域下单校验使用）。"""
        rows = await self._product_repository.get_purchasable_products(product_ids)
        return [
            PurchasableProduct(
                id=row["id"],
                shop_id=row["shop_id"],
                shop_name=row["shop_name"],
                name=row["name"],
                price=f"{row['price']:.2f}",
                stock=row["stock"],
                is_published=bool(row["is_published"]),
                shop_active=row["shop_status"] == "active",
                owner_user_id=row["owner_user_id"],
            )
            for row in rows
        ]

    async def get_products_for_engagement(
        self, product_ids: list[str]
    ) -> list[EngagementProduct]:
        """批量查询商品信息（供 engagement 域收藏列表 enrichment 与 POST 存在性校验）。

        仅返回 DB 存在的行；不过滤上架/店状态（偏好 ≠ 可购）。空列表输入返回 ``[]``。
        """
        rows = await self._product_repository.fetch_products_with_shop_by_ids(
            product_ids
        )
        if not rows:
            return []
        urls = await resolve_urls_batch(
            self._media_service, [row["primary_media_id"] for row in rows]
        )
        return [
            EngagementProduct(
                id=row["id"],
                shop_id=row["shop_id"],
                shop_name=row["shop_name"],
                name=row["name"],
                price=f"{row['price']:.2f}",
                image_url=(
                    urls.get(row["primary_media_id"])
                    if row["primary_media_id"] is not None
                    else None
                ),
                is_published=bool(row["is_published"]),
                shop_active=row["shop_status"] == "active",
            )
            for row in rows
        ]

    async def reserve_stock(self, items: list[tuple[str, int]]) -> None:
        """预留库存（供 ordering 域创建订单时调用）。"""
        try:
            await self._product_repository.reserve_stock(items)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    async def release_stock(self, items: list[tuple[str, int]]) -> None:
        """释放库存（供 ordering 域取消/过期时调用）。"""
        await self._product_repository.release_stock(items)

    async def validate_product_refs_for_shop(
        self,
        shop_id: uuid.UUID,
        product_ids: list[uuid.UUID],
    ) -> None:
        """校验 product refs 均属于该 shop；任一不存在或跨 shop → 422。

        不按公开可见性过滤：未上架商品若属于该 shop SHALL 视为合法。
        """
        if not product_ids:
            return
        products = await self._product_repository.get_by_ids(product_ids)
        found = {str(product.id): product for product in products}
        for product_id in product_ids:
            product = found.get(str(product_id))
            if product is None or str(product.shop_id) != str(shop_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_PRODUCT_REF_INVALID_MSG,
                )
