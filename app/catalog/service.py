"""catalog 域业务逻辑（店铺、类目、商品）。"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.catalog.models import Category, Product, Shop
from app.catalog.repository import CategoryRepository, ProductRepository, ShopRepository
from app.catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    PaginatedProducts,
    ProductCategoryItem,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    PurchasableProduct,
    ShopCreate,
    ShopResponse,
    ShopUpdate,
)

_USER_ALREADY_HAS_SHOP_MSG = "User already has a shop"
_SHOP_NAME_TAKEN_MSG = "Shop name already taken"
_SHOP_NOT_FOUND_MSG = "Shop not found"
_PRODUCT_NOT_FOUND_MSG = "Product not found"
_SHOP_CLOSED_MSG = "Shop is closed"
_CATEGORY_DUPLICATE_MSG = "Category name already exists under this parent"
_CATEGORY_NOT_FOUND_MSG = "One or more categories not found"
_CATEGORY_PARENT_NOT_FOUND_MSG = "Parent category not found"
_FORBIDDEN_PRODUCT_MSG = "Not allowed to modify this product"
_DEFAULT_PAGE_LIMIT = 20
_MAX_PAGE_LIMIT = 100


def _to_shop_response(shop: Shop) -> ShopResponse:
    """ORM 店铺转对外 DTO。"""
    return ShopResponse(
        id=str(shop.id),
        owner_user_id=str(shop.owner_user_id),
        name=shop.name,
        description=shop.description,
        logo_url=shop.logo_url,
        status=shop.status,
        created_at=shop.created_at,
        updated_at=shop.updated_at,
    )


def _to_category_response(category: Category) -> CategoryResponse:
    """ORM 类目转对外 DTO。"""
    return CategoryResponse(
        id=str(category.id),
        parent_id=str(category.parent_id) if category.parent_id is not None else None,
        name=category.name,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _format_price(price: Decimal) -> str:
    """将 DECIMAL 格式化为 API 价格字符串。"""
    return f"{price:.2f}"


def _to_product_response(
    product: Product,
    categories: list[ProductCategoryItem],
) -> ProductResponse:
    """ORM 商品转对外 DTO。"""
    return ProductResponse(
        id=str(product.id),
        shop_id=str(product.shop_id),
        name=product.name,
        description=product.description,
        price=_format_price(product.price),
        stock=product.stock,
        is_published=product.is_published,
        image_url=product.image_url,
        categories=categories,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    """规范化分页参数。"""
    safe_limit = min(max(limit, 1), _MAX_PAGE_LIMIT)
    safe_offset = max(offset, 0)
    return safe_limit, safe_offset


def _parse_category_ids(category_ids: list[str]) -> list[uuid.UUID]:
    """将请求体中的类目 ID 转为 UUID 列表。"""
    return [uuid.UUID(item) for item in category_ids]


class ShopService:
    """catalog 业务服务（店铺、类目、商品）。"""

    def __init__(
        self,
        repository: ShopRepository,
        category_repository: CategoryRepository,
        product_repository: ProductRepository,
    ) -> None:
        self._repository = repository
        self._category_repository = category_repository
        self._product_repository = product_repository

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

    async def create_category(self, data: CategoryCreate) -> CategoryResponse:
        """管理员创建类目。"""
        parent_id: uuid.UUID | None = None
        if data.parent_id is not None:
            parent_id = uuid.UUID(data.parent_id)
            parent = await self._category_repository.get_by_id(parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_CATEGORY_PARENT_NOT_FOUND_MSG,
                )

        duplicate = await self._category_repository.get_by_parent_and_name(
            parent_id, data.name
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CATEGORY_DUPLICATE_MSG,
            )

        try:
            category = await self._category_repository.create(
                category_id=uuid.uuid4(),
                name=data.name,
                parent_id=parent_id,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CATEGORY_DUPLICATE_MSG,
            ) from exc
        return _to_category_response(category)

    async def list_categories(self) -> list[CategoryResponse]:
        """返回扁平类目列表。"""
        categories = await self._category_repository.list_all()
        return [_to_category_response(item) for item in categories]

    async def create_product(self, shop: Shop, data: ProductCreate) -> ProductResponse:
        """店主在 active 店铺下创建商品。"""
        self._ensure_shop_active(shop)
        category_ids = _parse_category_ids(data.category_ids)
        primary_category_id = uuid.UUID(data.primary_category_id)
        await self._ensure_categories_exist(category_ids)

        product = await self._product_repository.create(
            product_id=uuid.uuid4(),
            shop_id=uuid.UUID(str(shop.id)),
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            is_published=data.is_published,
            image_url=data.image_url,
            category_ids=category_ids,
            primary_category_id=primary_category_id,
        )
        categories = await self._load_product_categories(uuid.UUID(str(product.id)))
        return _to_product_response(product, categories)

    async def update_product(
        self,
        product_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        data: ProductUpdate,
    ) -> ProductResponse:
        """店主更新本店商品。"""
        product = await self._product_repository.get_by_id(product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_PRODUCT_NOT_FOUND_MSG,
            )

        shop = await self._repository.get_by_id(uuid.UUID(str(product.shop_id)))
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_PRODUCT_NOT_FOUND_MSG,
            )
        if str(shop.owner_user_id) != str(owner_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_FORBIDDEN_PRODUCT_MSG,
            )
        self._ensure_shop_active(shop)

        if data.name is not None:
            product.name = data.name
        if data.description is not None:
            product.description = data.description
        if data.price is not None:
            product.price = data.price
        if data.stock is not None:
            product.stock = data.stock
        if data.image_url is not None:
            product.image_url = data.image_url
        if data.is_published is not None:
            product.is_published = data.is_published

        if data.category_ids is not None:
            assert data.primary_category_id is not None
            category_ids = _parse_category_ids(data.category_ids)
            primary_category_id = uuid.UUID(data.primary_category_id)
            await self._ensure_categories_exist(category_ids)
            await self._product_repository.replace_categories(
                product_id,
                category_ids,
                primary_category_id,
            )

        updated = await self._product_repository.save(product)
        categories = await self._load_product_categories(product_id)
        return _to_product_response(updated, categories)

    async def list_my_products(
        self,
        shop: Shop,
        *,
        limit: int = _DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedProducts:
        """分页返回店主店铺全部商品。"""
        safe_limit, safe_offset = _clamp_pagination(limit, offset)
        products, total = await self._product_repository.list_by_shop(
            uuid.UUID(str(shop.id)),
            limit=safe_limit,
            offset=safe_offset,
        )
        items: list[ProductResponse] = []
        for product in products:
            categories = await self._load_product_categories(
                uuid.UUID(str(product.id))
            )
            items.append(_to_product_response(product, categories))
        return PaginatedProducts(
            items=items,
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    async def list_public_products(
        self,
        *,
        category_id: uuid.UUID | None = None,
        limit: int = _DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedProducts:
        """分页返回公开可见商品。"""
        safe_limit, safe_offset = _clamp_pagination(limit, offset)
        products, total = await self._product_repository.list_public(
            category_id=category_id,
            limit=safe_limit,
            offset=safe_offset,
        )
        items: list[ProductResponse] = []
        for product in products:
            categories = await self._load_product_categories(
                uuid.UUID(str(product.id))
            )
            items.append(_to_product_response(product, categories))
        return PaginatedProducts(
            items=items,
            total=total,
            limit=safe_limit,
            offset=safe_offset,
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
        return _to_product_response(product, categories)

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

    async def reserve_stock(self, items: list[tuple[str, int]]) -> None:
        """预留库存（供 ordering 域创建订单时调用）。"""
        try:
            await self._product_repository.reserve_stock(items)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            )

    async def release_stock(self, items: list[tuple[str, int]]) -> None:
        """释放库存（供 ordering 域取消/过期时调用）。"""
        await self._product_repository.release_stock(items)

    async def create_shop(
        self,
        owner_user_id: uuid.UUID,
        data: ShopCreate,
    ) -> ShopResponse:
        """已认证用户创建店铺。"""
        existing_shop = await self._repository.get_by_owner_user_id(owner_user_id)
        if existing_shop is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_USER_ALREADY_HAS_SHOP_MSG,
            )

        name_conflict = await self._repository.get_by_name(data.name)
        if name_conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_SHOP_NAME_TAKEN_MSG,
            )

        shop = await self._repository.create(
            shop_id=uuid.uuid4(),
            owner_user_id=owner_user_id,
            name=data.name,
            description=data.description,
            logo_url=data.logo_url,
        )
        return _to_shop_response(shop)

    async def get_my_shop(self, owner_user_id: uuid.UUID) -> ShopResponse:
        """查询当前用户作为店主的店铺。"""
        shop = await self._repository.get_by_owner_user_id(owner_user_id)
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_SHOP_NOT_FOUND_MSG,
            )
        return _to_shop_response(shop)

    async def update_my_shop(self, shop: Shop, data: ShopUpdate) -> ShopResponse:
        """店主更新自己的店铺。"""
        if data.name is not None and data.name != shop.name:
            name_conflict = await self._repository.get_by_name(data.name)
            if name_conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_SHOP_NAME_TAKEN_MSG,
                )
            shop.name = data.name

        if data.description is not None:
            shop.description = data.description

        if data.logo_url is not None:
            shop.logo_url = data.logo_url

        if data.status is not None:
            shop.status = data.status

        updated = await self._repository.save(shop)
        return _to_shop_response(updated)

    async def get_public_shop(self, shop_id: uuid.UUID) -> ShopResponse:
        """公开查询店铺详情（含 closed 状态）。"""
        shop = await self._repository.get_by_id(shop_id)
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_SHOP_NOT_FOUND_MSG,
            )
        return _to_shop_response(shop)
