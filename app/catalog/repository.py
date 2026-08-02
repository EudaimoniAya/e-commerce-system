"""catalog 域持久化层。"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product, ProductCategory, Shop


class ShopRepository:
    """shops 表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, shop_id: uuid.UUID) -> Shop | None:
        """按主键查询店铺。"""
        return await self._session.get(Shop, str(shop_id))

    async def get_by_owner_user_id(self, owner_user_id: uuid.UUID) -> Shop | None:
        """按店主用户 ID 查询店铺。"""
        result = await self._session.execute(
            select(Shop).where(Shop.owner_user_id == str(owner_user_id))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Shop | None:
        """按店名查询店铺。"""
        result = await self._session.execute(
            select(Shop).where(Shop.name == name)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        shop_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        name: str,
        description: str | None,
        logo_url: str | None,
    ) -> Shop:
        """创建店铺并提交事务。"""
        shop = Shop(
            id=str(shop_id),
            owner_user_id=str(owner_user_id),
            name=name,
            description=description,
            logo_url=logo_url,
            status="active",
        )
        self._session.add(shop)
        await self._session.commit()
        await self._session.refresh(shop)
        return shop

    async def save(self, shop: Shop) -> Shop:
        """保存店铺变更并提交事务。"""
        await self._session.commit()
        await self._session.refresh(shop)
        return shop


class CategoryRepository:
    """categories 表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Category]:
        """返回全部类目（扁平列表）。"""
        result = await self._session.execute(select(Category))
        return list(result.scalars().all())

    async def get_by_id(self, category_id: uuid.UUID) -> Category | None:
        """按主键查询类目。"""
        return await self._session.get(Category, str(category_id))

    async def get_by_parent_and_name(
        self,
        parent_id: uuid.UUID | None,
        name: str,
    ) -> Category | None:
        """按 parent_id 与 name 查询同级类目（兼容 MySQL NULL parent UNIQUE 语义）。"""
        query = select(Category).where(Category.name == name)
        if parent_id is None:
            query = query.where(Category.parent_id.is_(None))
        else:
            query = query.where(Category.parent_id == str(parent_id))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def count_existing(self, category_ids: list[uuid.UUID]) -> int:
        """统计给定 ID 中存在于库中的类目数量。"""
        if not category_ids:
            return 0
        id_strs = [str(item) for item in category_ids]
        result = await self._session.execute(
            select(func.count())
            .select_from(Category)
            .where(Category.id.in_(id_strs))
        )
        return int(result.scalar_one())

    async def create(
        self,
        *,
        category_id: uuid.UUID,
        name: str,
        parent_id: uuid.UUID | None,
    ) -> Category:
        """创建类目并提交事务。"""
        category = Category(
            id=str(category_id),
            name=name,
            parent_id=str(parent_id) if parent_id is not None else None,
        )
        self._session.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category


class ProductRepository:
    """products 与 product_categories 表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        """按主键查询商品。"""
        return await self._session.get(Product, str(product_id))

    async def create(
        self,
        *,
        product_id: uuid.UUID,
        shop_id: uuid.UUID,
        name: str,
        description: str | None,
        price: Decimal,
        stock: int,
        is_published: bool,
        image_url: str | None,
        category_ids: list[uuid.UUID],
        primary_category_id: uuid.UUID,
    ) -> Product:
        """创建商品及类目关联并提交事务。"""
        product = Product(
            id=str(product_id),
            shop_id=str(shop_id),
            name=name,
            description=description,
            price=price,
            stock=stock,
            is_published=is_published,
            image_url=image_url,
        )
        self._session.add(product)
        await self._session.flush()
        for category_id in category_ids:
            self._session.add(
                ProductCategory(
                    product_id=str(product_id),
                    category_id=str(category_id),
                    is_primary=category_id == primary_category_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def save(self, product: Product) -> Product:
        """保存商品变更并提交事务。"""
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def replace_categories(
        self,
        product_id: uuid.UUID,
        category_ids: list[uuid.UUID],
        primary_category_id: uuid.UUID,
    ) -> None:
        """全量替换商品类目关联。"""
        await self._session.execute(
            delete(ProductCategory).where(
                ProductCategory.product_id == str(product_id)
            )
        )
        for category_id in category_ids:
            self._session.add(
                ProductCategory(
                    product_id=str(product_id),
                    category_id=str(category_id),
                    is_primary=category_id == primary_category_id,
                )
            )
        await self._session.commit()

    async def get_category_items(
        self, product_id: uuid.UUID
    ) -> list[tuple[str, str, bool]]:
        """查询商品关联类目（id, name, is_primary）。"""
        result = await self._session.execute(
            select(Category.id, Category.name, ProductCategory.is_primary)
            .join(ProductCategory, ProductCategory.category_id == Category.id)
            .where(ProductCategory.product_id == str(product_id))
        )
        return [(str(row[0]), row[1], bool(row[2])) for row in result.all()]

    async def list_by_shop(
        self,
        shop_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        """分页查询店铺全部商品。"""
        base = select(Product).where(Product.shop_id == str(shop_id))
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await self._session.execute(
            base.order_by(Product.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    def _public_base_query(self, category_id: uuid.UUID | None):
        """公开商品列表/详情的公共过滤条件。"""
        query = (
            select(Product)
            .join(Shop, Product.shop_id == Shop.id)
            .where(Product.is_published.is_(True))
            .where(Shop.status == "active")
        )
        if category_id is not None:
            query = query.join(
                ProductCategory,
                ProductCategory.product_id == Product.id,
            ).where(ProductCategory.category_id == str(category_id))
        return query.distinct()

    async def list_public(
        self,
        *,
        category_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        """分页查询已上架且店铺 active 的公开商品。"""
        base = self._public_base_query(category_id)
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await self._session.execute(
            base.order_by(Product.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    async def get_public_by_id(self, product_id: uuid.UUID) -> Product | None:
        """查询公开可见的商品详情。"""
        query = self._public_base_query(None).where(Product.id == str(product_id))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def fetch_products_with_shop_by_ids(
        self, product_ids: list[str]
    ) -> list[dict]:
        """批量查询商品及所属店铺信息（共用行）。

        供 ``get_purchasable_products``（ordering）与 ``get_products_for_engagement``
        （engagement）各自映射 DTO。仅返回 DB 存在的行；不过滤上架/店状态。
        空列表输入返回 ``[]``。
        """
        if not product_ids:
            return []
        result = await self._session.execute(
            select(
                Product.id,
                Product.shop_id,
                Product.name,
                Product.price,
                Product.stock,
                Product.is_published,
                Product.image_url,
                Shop.name.label("shop_name"),
                Shop.status.label("shop_status"),
                Shop.owner_user_id,
            )
            .join(Shop, Product.shop_id == Shop.id)
            .where(Product.id.in_(product_ids))
        )
        return [
            {
                "id": str(row.id),
                "shop_id": str(row.shop_id),
                "name": row.name,
                "price": row.price,
                "stock": row.stock,
                "is_published": row.is_published,
                "image_url": row.image_url,
                "shop_name": row.shop_name,
                "shop_status": row.shop_status,
                "owner_user_id": str(row.owner_user_id),
            }
            for row in result.all()
        ]

    async def get_purchasable_products(
        self, product_ids: list[str]
    ) -> list[dict]:
        """批量查询商品及所属店铺信息（供 ordering 下单校验用；行为与 history 一致）。"""
        return await self.fetch_products_with_shop_by_ids(product_ids)

    async def reserve_stock(self, items: list[tuple[str, int]]) -> None:
        """条件扣减库存（供 ordering 域预留调用；不提交事务）。"""
        for product_id, qty in items:
            stmt = (
                update(Product)
                .where(Product.id == product_id)
                .where(Product.stock >= qty)
                .values(stock=Product.stock - qty)
            )
            result = await self._session.execute(stmt)
            if result.rowcount == 0:
                msg = f"Insufficient stock for product {product_id}"
                raise ValueError(msg)

    async def release_stock(self, items: list[tuple[str, int]]) -> None:
        """加回库存（供 ordering 域取消/过期时调用；不提交事务）。"""
        for product_id, qty in items:
            stmt = (
                update(Product)
                .where(Product.id == product_id)
                .values(stock=Product.stock + qty)
            )
            await self._session.execute(stmt)
