"""catalog 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Shop
from app.catalog.repository import ShopRepository
from app.catalog.service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.database import get_db

_SHOP_NOT_FOUND_MSG = "Shop not found"


def get_shop_repository(
    session: AsyncSession = Depends(get_db),
) -> ShopRepository:
    """注入 catalog 仓储。"""
    return ShopRepository(session)


def get_shop_service(
    repository: ShopRepository = Depends(get_shop_repository),
) -> ShopService:
    """注入 catalog 服务。"""
    return ShopService(repository)


async def get_current_shop(
    user_id: uuid.UUID = Depends(get_current_user_id),
    repository: ShopRepository = Depends(get_shop_repository),
) -> Shop:
    """解析 JWT 并查库返回当前用户的店铺；无店时 404。"""
    shop = await repository.get_by_owner_user_id(user_id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_SHOP_NOT_FOUND_MSG,
        )
    return shop
