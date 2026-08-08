"""catalog 域请求/响应 DTO。"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.infra.pagination.schemas import Paginated


class ShopCreate(BaseModel):
    """开店请求体。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    logo_media_id: str | None = Field(default=None, max_length=36)


class ShopUpdate(BaseModel):
    """更新店铺请求体（部分字段可选）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    logo_media_id: str | None = Field(default=None, max_length=36)
    status: Literal["active", "closed"] | None = None


class ShopResponse(BaseModel):
    """对外店铺资料。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_user_id: str
    name: str
    description: str | None
    logo_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CategoryCreate(BaseModel):
    """创建类目请求体。"""

    name: str = Field(min_length=1, max_length=64)
    parent_id: str | None = None


class CategoryResponse(BaseModel):
    """对外类目资料。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    name: str
    created_at: datetime
    updated_at: datetime


class ProductCategoryItem(BaseModel):
    """商品关联类目摘要。"""

    id: str
    name: str
    is_primary: bool


class ProductCreate(BaseModel):
    """创建商品请求体。"""

    name: str = Field(min_length=1, max_length=128)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(gt=0)
    description: str | None = None
    primary_media_id: str | None = Field(default=None, max_length=36)
    is_published: bool = False
    category_ids: list[str] = Field(min_length=1)
    primary_category_id: str

    @model_validator(mode="after")
    def validate_primary_in_categories(self) -> Self:
        """primary_category_id 必须属于 category_ids。"""
        if self.primary_category_id not in self.category_ids:
            msg = "primary_category_id must be in category_ids"
            raise ValueError(msg)
        return self

    @field_validator("category_ids")
    @classmethod
    def validate_category_uuids(cls, value: list[str]) -> list[str]:
        """校验 category_ids 为合法 UUID。"""
        for item in value:
            uuid.UUID(item)
        return value

    @field_validator("primary_category_id")
    @classmethod
    def validate_primary_uuid(cls, value: str) -> str:
        """校验 primary_category_id 为合法 UUID。"""
        uuid.UUID(value)
        return value


class ProductUpdate(BaseModel):
    """更新商品请求体（部分字段可选）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    description: str | None = None
    primary_media_id: str | None = Field(default=None, max_length=36)
    is_published: bool | None = None
    category_ids: list[str] | None = None
    primary_category_id: str | None = None

    @model_validator(mode="after")
    def validate_category_fields(self) -> Self:
        """若提供类目字段，则 category_ids 至少 1 个且 primary 须在其中。"""
        has_categories = self.category_ids is not None
        has_primary = self.primary_category_id is not None
        if has_categories != has_primary:
            msg = "category_ids and primary_category_id must be provided together"
            raise ValueError(msg)
        if self.category_ids is not None:
            if len(self.category_ids) < 1:
                msg = "category_ids must contain at least one item"
                raise ValueError(msg)
            assert self.primary_category_id is not None
            if self.primary_category_id not in self.category_ids:
                msg = "primary_category_id must be in category_ids"
                raise ValueError(msg)
            for item in self.category_ids:
                uuid.UUID(item)
            uuid.UUID(self.primary_category_id)
        return self


class ProductResponse(BaseModel):
    """对外商品资料。"""

    id: str
    shop_id: str
    name: str
    description: str | None
    price: str
    stock: int
    is_published: bool
    image_url: str | None
    categories: list[ProductCategoryItem]
    created_at: datetime
    updated_at: datetime


class PurchasableProduct(BaseModel):
    """可购商品查询 DTO（供 ordering 域下单校验使用，不泄漏 ORM 实例）。"""

    id: str
    shop_id: str
    shop_name: str
    name: str
    price: str
    stock: int
    is_published: bool
    shop_active: bool
    owner_user_id: str


class EngagementProduct(BaseModel):
    """跨域 DTO：供 engagement 域收藏列表 enrichment 使用（无 HTTP 路由，不泄漏 ORM 实例）。"""

    id: str
    shop_id: str
    shop_name: str
    name: str
    price: str
    image_url: (
        str | None
    )  # 保留字段名（engagement 零改动）；值由 primary_media_id 经 media.service.resolve_urls 填充
    is_published: bool
    shop_active: bool


class ShopSupportContext(BaseModel):
    """跨域 DTO：供 support 域会话创建与校验使用（无 HTTP 路由，不泄漏 ORM 实例）。"""

    id: str
    status: str  # active | closed
    owner_user_id: str


class PaginatedProducts(Paginated[ProductResponse]):
    """分页商品列表。"""

    model_config = ConfigDict(title="PaginatedProducts")
