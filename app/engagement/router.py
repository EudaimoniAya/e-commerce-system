"""engagement 域收藏 + 浏览 REST 端点（JWT 隐式用户，URL 不含 user_id）。"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi.responses import JSONResponse

from app.engagement.deps import get_browse_service, get_favorite_service
from app.engagement.schemas import (
    BatchDeleteFavoritesRequest,
    BatchDeleteFavoritesResponse,
    BrowseAcceptedResponse,
    BrowseListResponse,
    BrowseRecordRequest,
    FavoriteCreateRequest,
    FavoriteItem,
    FavoriteListResponse,
)
from app.engagement.service import BrowseService, FavoriteService
from app.infra.auth import get_current_user_id
from app.infra.pagination.deps import get_pagination_params
from app.infra.pagination.schemas import PaginationParams

router = APIRouter(tags=["favorites"])


@router.post("/favorites", response_model=FavoriteItem)
async def add_favorite(
    body: FavoriteCreateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> JSONResponse:
    """收藏商品（首次→201，重复→200 幂等）。"""
    favorite, created = await service.add_favorite(
        user_id=user_id,
        product_id=body.product_id,
    )
    return JSONResponse(
        content=favorite.model_dump(mode="json"),
        status_code=201 if created else 200,
    )


@router.get("/favorites", response_model=FavoriteListResponse)
async def list_favorites(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> FavoriteListResponse:
    """分页收藏列表（items + unavailable_items）。"""
    return await service.list_favorites(
        user_id=user_id,
        limit=params.limit,
        offset=params.offset,
    )


@router.delete("/favorites/{product_id}", status_code=204)
async def remove_favorite(
    product_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> Response:
    """取消收藏（按商品）。"""
    await service.delete_favorite(
        user_id=user_id,
        product_id=str(product_id),
    )
    return Response(status_code=204)


@router.post(
    "/favorites/batch-delete",
    response_model=BatchDeleteFavoritesResponse,
)
async def batch_delete_favorites(
    body: BatchDeleteFavoritesRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> BatchDeleteFavoritesResponse:
    """批量取消收藏（前端从 unavailable_items 收集 product_ids 提交）。"""
    deleted_count = await service.batch_delete_favorites(
        user_id=user_id,
        product_ids=body.product_ids,
    )
    return BatchDeleteFavoritesResponse(deleted_count=deleted_count)


# ── 浏览（user_browse_history）────────────────────────────────


@router.post(
    "/browse",
    response_model=BrowseAcceptedResponse,
    status_code=202,
    tags=["browse"],
)
async def record_browse(
    body: BrowseRecordRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: BrowseService = Depends(get_browse_service),
) -> BrowseAcceptedResponse:
    """记录浏览：catalog 校验后经 BackgroundTasks 异步 upsert，受理即 202。

    202 不代表已落库（最终一致）；``catalog`` 无此商品 → 422 且不调度。
    """
    await service.record_browse(
        user_id=user_id,
        product_id=body.product_id,
        background_tasks=background_tasks,
    )
    return BrowseAcceptedResponse(accepted=True)


@router.get("/browse", response_model=BrowseListResponse, tags=["browse"])
async def list_browses(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: BrowseService = Depends(get_browse_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> BrowseListResponse:
    """分页浏览历史（items + unavailable_items，按 last_viewed_at 降序）。"""
    return await service.list_browses(
        user_id=user_id,
        limit=params.limit,
        offset=params.offset,
    )


@router.delete("/browse/{product_id}", status_code=204, tags=["browse"])
async def remove_browse(
    product_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: BrowseService = Depends(get_browse_service),
) -> Response:
    """删除单条浏览记录（误触清理）；无记录 → 404。"""
    await service.delete_browse(
        user_id=user_id,
        product_id=str(product_id),
    )
    return Response(status_code=204)
