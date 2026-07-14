"""catalog 域业务逻辑（店铺开店、查询、更新）。"""

import uuid

from fastapi import HTTPException, status

from app.catalog.models import Shop
from app.catalog.repository import ShopRepository
from app.catalog.schemas import ShopCreate, ShopResponse, ShopUpdate

_USER_ALREADY_HAS_SHOP_MSG = "User already has a shop"
_SHOP_NAME_TAKEN_MSG = "Shop name already taken"
_SHOP_NOT_FOUND_MSG = "Shop not found"


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


class ShopService:
    """店铺业务服务。"""

    def __init__(self, repository: ShopRepository) -> None:
        self._repository = repository

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
