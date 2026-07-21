"""ordering 域请求/响应 DTO（供 API 与 integration 测试 builders 使用）。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderItemCreate(BaseModel):
    """下单行：商品与数量。"""

    product_id: str
    qty: int = Field(ge=1)

    @field_validator("product_id")
    @classmethod
    def validate_product_uuid(cls, value: str) -> str:
        """校验 product_id 为合法 UUID。"""
        uuid.UUID(value)
        return value


class OrderCreate(BaseModel):
    """买家创建订单请求体。"""

    items: list[OrderItemCreate] = Field(min_length=1)


class SellerOrderCreate(BaseModel):
    """卖家为指定买家创建订单请求体。"""

    buyer_user_id: str
    items: list[OrderItemCreate] = Field(min_length=1)

    @field_validator("buyer_user_id")
    @classmethod
    def validate_buyer_uuid(cls, value: str) -> str:
        """校验 buyer_user_id 为合法 UUID。"""
        uuid.UUID(value)
        return value


class OrderItemResponse(BaseModel):
    """订单行快照。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product_name: str
    unit_price: str
    qty: int


class OrderResponse(BaseModel):
    """对外订单资料。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    buyer_user_id: str
    shop_id: str
    initiated_by: Literal["buyer", "seller"]
    status: Literal[
        "awaiting_payment",
        "confirmed",
        "shipped",
        "completed",
        "cancelled",
    ]
    cancel_reason: str | None
    total_amount: str
    expires_at: datetime
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime


class ShipmentCreate(BaseModel):
    """卖家发货请求体（可空对象或可选备注）。"""

    note: str | None = Field(default=None, max_length=512)


class PaginatedOrders(BaseModel):
    """分页订单列表。"""

    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
