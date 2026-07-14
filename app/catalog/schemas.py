"""catalog 域请求/响应 DTO。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShopCreate(BaseModel):
    """开店请求体。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=512)


class ShopUpdate(BaseModel):
    """更新店铺请求体（部分字段可选）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=512)
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
