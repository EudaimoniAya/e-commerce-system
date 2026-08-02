"""``ShopService.get_products_for_engagement`` 字段映射单元测试。

对齐 spec（catalog-products "Batch product lookup for engagement"）中字段相关的
scenario：完整字段映射、不过滤上架/店状态、不存在 id 不在返回列表。
使用 AsyncMock 注入 ``product_repository``，不触碰数据库（沿用 test_sms_service.py 先例）。
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import allure
import pytest

from app.catalog.schemas import EngagementProduct
from app.catalog.service import ShopService


def _full_row(**overrides: object) -> dict:
    """构造 repository 返回的完整行 dict（fetch_products_with_shop_by_ids 的契约）。"""
    row: dict = {
        "id": "11111111-1111-4111-8111-111111111111",
        "shop_id": "22222222-2222-4222-8222-222222222222",
        "name": "测试商品",
        "price": Decimal("99.00"),
        "stock": 10,
        "is_published": True,
        "image_url": "https://cdn.example.com/a.jpg",
        "shop_name": "测试店铺",
        "shop_status": "active",
        "owner_user_id": "33333333-3333-4333-8333-333333333333",
    }
    row.update(overrides)
    return row


@pytest.fixture
def mock_product_repository() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def shop_service(mock_product_repository: AsyncMock) -> ShopService:
    """注入 mock 的 product_repository；其余 repository 不参与本方法。"""
    return ShopService(
        repository=AsyncMock(),
        category_repository=AsyncMock(),
        product_repository=mock_product_repository,
    )


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("映射出完整 EngagementProduct 字段。")
@pytest.mark.asyncio
async def test_maps_all_engagement_fields(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """EngagementProduct 含 spec 要求的 8 字段，且为 schema 实例（不泄漏 ORM/dict）。"""
    row = _full_row()
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [row]

    products = await shop_service.get_products_for_engagement([row["id"]])

    assert len(products) == 1
    product = products[0]
    assert isinstance(product, EngagementProduct)
    assert product.id == row["id"]
    assert product.shop_id == row["shop_id"]
    assert product.shop_name == row["shop_name"]
    assert product.name == row["name"]
    assert product.price == "99.00"  # Decimal 字符串化（两位小数）
    assert product.image_url == row["image_url"]
    assert product.is_published is True
    assert product.shop_active is True


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("price 以两位小数字符串返回。")
@pytest.mark.asyncio
async def test_price_formatted_as_two_decimal_string(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """price 映射为两位小数字符串（149.5 → \"149.50\"）。"""
    row = _full_row(price=Decimal("149.5"))
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [row]

    products = await shop_service.get_products_for_engagement([row["id"]])

    assert products[0].price == "149.50"


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("image_url 为空时保持 None。")
@pytest.mark.asyncio
async def test_image_url_none_preserved(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """可空 image_url 保留 None，不做占位填充。"""
    row = _full_row(image_url=None)
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [row]

    products = await shop_service.get_products_for_engagement([row["id"]])

    assert products[0].image_url is None


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("未上架商品仍被返回且标记 is_published=false。")
@pytest.mark.asyncio
async def test_unpublished_product_still_returned(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """查询不过滤上架状态：is_published=false 的行仍在返回列表。"""
    row = _full_row(is_published=False)
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [row]

    products = await shop_service.get_products_for_engagement([row["id"]])

    assert len(products) == 1  # 未上架不被过滤
    assert products[0].is_published is False


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("关店商品仍被返回且 shop_active=false。")
@pytest.mark.asyncio
async def test_closed_shop_product_still_returned(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """查询不过滤店铺状态：shop_status=closed 时 shop_active=false，仍在返回列表。"""
    row = _full_row(shop_status="closed")
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [row]

    products = await shop_service.get_products_for_engagement([row["id"]])

    assert len(products) == 1  # 关店不被过滤
    assert products[0].shop_active is False


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("repository 无结果时返回空列表。")
@pytest.mark.asyncio
async def test_empty_result_returns_empty_list(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """repository 未命中时返回空列表，并透传入参到 repository。"""
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = []

    products = await shop_service.get_products_for_engagement(["anything"])

    assert products == []
    mock_product_repository.fetch_products_with_shop_by_ids.assert_awaited_once_with(
        ["anything"]
    )


@allure.epic("catalog")
@allure.feature("engagement_product_service")
@allure.title("不存在的 id 不出现在返回列表。")
@pytest.mark.asyncio
async def test_missing_id_not_in_result(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """service 忠实映射 repository 过滤结果：未命中 id 不出现、不补全。"""
    existing = _full_row()
    mock_product_repository.fetch_products_with_shop_by_ids.return_value = [existing]

    products = await shop_service.get_products_for_engagement(
        [existing["id"], "missing-id"]
    )

    assert [p.id for p in products] == [existing["id"]]
