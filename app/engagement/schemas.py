"""engagement 域 Pydantic schema（收藏 API 请求/响应）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FavoriteItem(BaseModel):
    """收藏行（items 侧）。

    不含 product 详情——前端对可展示项调公开 ``GET /products/{id}``。
    """

    id: str
    product_id: str
    created_at: datetime


class UnavailableFavoriteItem(BaseModel):
    """失效收藏行（unavailable_items 侧）。

    ``product_name`` / ``image_url`` 来自 ``EngagementProduct`` 读时 enrichment，非 DB 快照；
    ``not_found`` 时 ``product_name`` 可能为空。
    """

    id: str
    product_id: str
    created_at: datetime
    reason: Literal["not_found", "product_unpublished", "shop_closed"]
    product_name: str | None
    image_url: str | None


class FavoriteListResponse(BaseModel):
    """GET /favorites 分页响应（total 计该用户全部 favorite 行，含 unavailable）。"""

    items: list[FavoriteItem]
    unavailable_items: list[UnavailableFavoriteItem]
    total: int
    limit: int
    offset: int


class FavoriteCreateRequest(BaseModel):
    """POST /favorites 请求体。"""

    product_id: str


class BatchDeleteFavoritesRequest(BaseModel):
    """POST /favorites/batch-delete 请求体（与 batch-pay 空列表约定一致）。"""

    product_ids: list[str] = Field(min_length=1)


class BatchDeleteFavoritesResponse(BaseModel):
    """POST /favorites/batch-delete 响应。"""

    deleted_count: int
