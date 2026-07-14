"""catalog 域 HTTP 路由（店铺）。"""

import uuid

from fastapi import APIRouter, Depends, status

from app.catalog.deps import get_current_shop, get_shop_service
from app.catalog.models import Shop
from app.catalog.schemas import ShopCreate, ShopResponse, ShopUpdate
from app.catalog.service import ShopService
from app.infra.auth import get_current_user_id

router = APIRouter(tags=["shops"])


@router.post(
    "/shops",
    response_model=ShopResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shop(
    body: ShopCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """已认证用户创建店铺。"""
    return await service.create_shop(user_id, body)


@router.get("/shops/me", response_model=ShopResponse)
async def read_my_shop(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """返回当前用户作为店主的店铺。"""
    return await service.get_my_shop(user_id)


@router.patch("/shops/me", response_model=ShopResponse)
async def update_my_shop(
    body: ShopUpdate,
    shop: Shop = Depends(get_current_shop),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """店主更新自己的店铺。"""
    return await service.update_my_shop(shop, body)


@router.get("/shops/{shop_id}", response_model=ShopResponse)
async def read_public_shop(
    shop_id: uuid.UUID,
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """公开查询店铺详情。"""
    return await service.get_public_shop(shop_id)
