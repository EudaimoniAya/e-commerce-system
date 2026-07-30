"""catalog 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Shop
from app.catalog.repository import (
    CategoryRepository,
    ProductRepository,
    ShopRepository,
)
from app.catalog.service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.database import get_db

_SHOP_NOT_FOUND_MSG = "Shop not found"


def get_shop_repository(
    session: AsyncSession = Depends(get_db),
) -> ShopRepository:
    """注入 shop 仓储。"""
    return ShopRepository(session)


def get_category_repository(
    session: AsyncSession = Depends(get_db),
) -> CategoryRepository:
    """注入 category 仓储。"""
    return CategoryRepository(session)


def get_product_repository(
    session: AsyncSession = Depends(get_db),
) -> ProductRepository:
    """注入 product 仓储。"""
    return ProductRepository(session)


def get_shop_service(
    repository: ShopRepository = Depends(get_shop_repository),
    category_repository: CategoryRepository = Depends(get_category_repository),
    product_repository: ProductRepository = Depends(get_product_repository),
) -> ShopService:
    """注入 catalog 服务。"""
    return ShopService(repository, category_repository, product_repository)


async def get_current_shop(
    user_id: uuid.UUID = Depends(get_current_user_id),
    repository: ShopRepository = Depends(get_shop_repository),
) -> Shop:
    """解析 JWT 并查库返回当前用户的店铺；无店时 404。

    当前授权基于 ``shops.owner_user_id``（单人店 MVP）。组织层（Merchant +
    MerchantMember）演进见 ADR-007（``docs/decision/ADR-007-多租户扩展-设计与暂缓计划.md``）。
    """
    shop = await repository.get_by_owner_user_id(user_id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_SHOP_NOT_FOUND_MSG,
        )
    return shop
