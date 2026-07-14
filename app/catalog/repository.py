"""catalog 域持久化层。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Shop


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
