"""catalog 域 request schema 格式边界单元测试。"""

import uuid
from decimal import Decimal
from typing import Any

import allure
import pytest
from pydantic import ValidationError

from app.catalog.schemas import ProductCreate


def _valid_product_create_kwargs(**overrides: object) -> dict[str, Any]:
    """构造 ProductCreate 合法 baseline，供 override 非法字段。"""
    category_id = str(uuid.uuid4())
    base: dict[str, Any] = {
        "name": "p",
        "price": Decimal("99.00"),
        "stock": 10,
        "category_ids": [category_id],
        "primary_category_id": category_id,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(_valid_product_create_kwargs(category_ids=[]), id="empty_category_ids"),
        pytest.param(
            _valid_product_create_kwargs(
                category_ids=[str(uuid.uuid4())],
                primary_category_id=str(uuid.uuid4()),
            ),
            id="primary_not_in_list",
        ),
    ],
)
@allure.epic("catalog")
@allure.feature("catalog_schema")
@allure.title("ProductCreate 对非法 category 规则抛出 ValidationError")
def test_product_create_rejects_invalid_category_rules(kwargs: dict[str, Any]) -> None:
    """ProductCreate 对非法 category 规则抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        ProductCreate(**kwargs)
