"""catalog 域店铺业务逻辑（ShopService）。"""

import uuid

from fastapi import HTTPException, status

from app.catalog._media import resolve_single_url
from app.catalog.models import Shop
from app.catalog.repository import ShopRepository
from app.catalog.schemas import ShopContext, ShopCreate, ShopResponse, ShopUpdate
from app.media.service import MediaService

_USER_ALREADY_HAS_SHOP_MSG = "User already has a shop"
_SHOP_NAME_TAKEN_MSG = "Shop name already taken"
_SHOP_NOT_FOUND_MSG = "Shop not found"


def _to_shop_response(
    shop: Shop,
    logo_url: str | None = None,
) -> ShopResponse:
    """ORM 店铺转对外 DTO（logo_url 由调用方经 media 域 resolve 后传入）。"""
    return ShopResponse(
        id=str(shop.id),
        owner_user_id=str(shop.owner_user_id),
        name=shop.name,
        description=shop.description,
        logo_url=logo_url,
        status=shop.status,
        created_at=shop.created_at,
        updated_at=shop.updated_at,
    )


class ShopService:
    """catalog 域店铺业务服务（仅 shop repo + media）。"""

    def __init__(
        self,
        repository: ShopRepository,
        media_service: MediaService,
    ) -> None:
        self._repository = repository
        self._media_service = media_service

    async def create_shop(
        self,
        owner_user_id: uuid.UUID,
        data: ShopCreate,
    ) -> ShopResponse:
        """已认证用户创建店铺。

        设置 ``logo_media_id`` 时经 media attach 校验（owner 403 / ``image/*`` 422），
        成功后同事务 ``mark_public``；响应 logo_url 经 media 域 resolve。
        """
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

        if data.logo_media_id is not None:
            await self._media_service.assert_owned_by(
                data.logo_media_id, str(owner_user_id)
            )
            await self._media_service.assert_image_content_type(data.logo_media_id)
            await self._media_service.mark_public(data.logo_media_id)

        shop = await self._repository.create(
            shop_id=uuid.uuid4(),
            owner_user_id=owner_user_id,
            name=data.name,
            description=data.description,
            logo_media_id=data.logo_media_id,
        )
        logo_url = await resolve_single_url(self._media_service, shop.logo_media_id)
        return _to_shop_response(shop, logo_url=logo_url)

    async def get_my_shop(self, owner_user_id: uuid.UUID) -> ShopResponse:
        """查询当前用户作为店主的店铺。"""
        shop = await self._repository.get_by_owner_user_id(owner_user_id)
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_SHOP_NOT_FOUND_MSG,
            )
        logo_url = await resolve_single_url(self._media_service, shop.logo_media_id)
        return _to_shop_response(shop, logo_url=logo_url)

    async def update_my_shop(self, shop: Shop, data: ShopUpdate) -> ShopResponse:
        """店主更新自己的店铺。

        ``logo_media_id`` 显式 null 清空 logo；设置时经 media attach 校验
        （owner 403 / ``image/*`` 422）并同事务 ``mark_public``。
        """
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

        updates = data.model_dump(exclude_unset=True)
        if "logo_media_id" in updates:
            new_logo = updates["logo_media_id"]
            if new_logo is not None:
                await self._media_service.assert_owned_by(
                    new_logo, str(shop.owner_user_id)
                )
                await self._media_service.assert_image_content_type(new_logo)
                await self._media_service.mark_public(new_logo)
            shop.logo_media_id = new_logo

        if data.status is not None:
            shop.status = data.status

        updated = await self._repository.save(shop)
        logo_url = await resolve_single_url(self._media_service, updated.logo_media_id)
        return _to_shop_response(updated, logo_url=logo_url)

    async def get_public_shop(self, shop_id: uuid.UUID) -> ShopResponse:
        """公开查询店铺详情（含 closed 状态）。"""
        shop = await self._repository.get_by_id(shop_id)
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_SHOP_NOT_FOUND_MSG,
            )
        logo_url = await resolve_single_url(self._media_service, shop.logo_media_id)
        return _to_shop_response(shop, logo_url=logo_url)

    async def get_shop_context(self, shop_id: uuid.UUID) -> ShopContext:
        """返回店铺上下文（id / status / owner_user_id）；shop 不存在时 404。

        跨域 service（无 HTTP 路由）：product service / support 域注入本方法即可，
        禁止 import catalog ORM。
        """
        shop = await self._repository.get_by_id(shop_id)
        if shop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_SHOP_NOT_FOUND_MSG,
            )
        return ShopContext(
            id=str(shop.id),
            status=shop.status,
            owner_user_id=str(shop.owner_user_id),
        )
