"""catalog 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.category_service import CategoryService
from app.catalog.models import Shop
from app.catalog.product_service import ProductService
from app.catalog.repository import (
    CategoryRepository,
    ProductRepository,
    ShopRepository,
)
from app.catalog.shop_service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.database import get_db
from app.media.deps import get_media_service
from app.media.service import MediaService

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


def get_category_service(
    repository: CategoryRepository = Depends(get_category_repository),
) -> CategoryService:
    """注入类目服务（仅 category repo；无 media）。"""
    return CategoryService(repository)


def get_shop_service(
    repository: ShopRepository = Depends(get_shop_repository),
    media_service: MediaService = Depends(get_media_service),
) -> ShopService:
    """注入店铺服务（仅 shop repo + media）。"""
    return ShopService(repository, media_service)


def get_product_service(
    product_repository: ProductRepository = Depends(get_product_repository),
    category_repository: CategoryRepository = Depends(get_category_repository),
    media_service: MediaService = Depends(get_media_service),
    shop_service: ShopService = Depends(get_shop_service),
) -> ProductService:
    """注入商品服务（product + category repo + media；shop 校验经 ShopService）。"""
    return ProductService(
        product_repository,
        category_repository,
        media_service,
        shop_service,
    )


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
