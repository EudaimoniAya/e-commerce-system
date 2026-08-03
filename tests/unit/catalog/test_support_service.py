"""``ShopService`` support 跨域方法单元测试（get_shop_for_support / validate_product_refs_for_shop）。

对齐 catalog-products spec "Shop support context service method" 与
"Product refs validation for support" 的 scenario：上下文字段、404、422、未上架允许。
使用 AsyncMock 注入 repository，不触碰数据库（沿用 test_engagement_product_service.py 先例）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import allure
import pytest
from fastapi import HTTPException

from app.catalog.schemas import ShopSupportContext
from app.catalog.service import ShopService


@pytest.fixture
def mock_repository() -> AsyncMock:
    """mock ShopRepository。"""
    return AsyncMock()


@pytest.fixture
def mock_product_repository() -> AsyncMock:
    """mock ProductRepository。"""
    return AsyncMock()


@pytest.fixture
def shop_service(
    mock_repository: AsyncMock,
    mock_product_repository: AsyncMock,
) -> ShopService:
    """注入 mock 的 repository；category_repository 不参与本组方法。"""
    return ShopService(
        repository=mock_repository,
        category_repository=AsyncMock(),
        product_repository=mock_product_repository,
    )


def _fake_shop(*, status: str = "active") -> SimpleNamespace:
    """构造 ShopRepository.get_by_id 返回的 Shop 替代对象。"""
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        owner_user_id=uuid4(),
    )


def _fake_product(*, shop_id: str) -> SimpleNamespace:
    """构造 ProductRepository.get_by_ids 返回的 Product 替代对象。"""
    return SimpleNamespace(id=uuid4(), shop_id=shop_id)


# ── get_shop_for_support ──────────────────────────────────────


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("get_shop_for_support 返回 ShopSupportContext 字段一致。")
@pytest.mark.asyncio
async def test_get_shop_for_support_returns_context(
    shop_service: ShopService,
    mock_repository: AsyncMock,
) -> None:
    """shop 存在时返回 ShopSupportContext，字段与 DB 一致。"""
    shop = _fake_shop()
    mock_repository.get_by_id.return_value = shop

    context = await shop_service.get_shop_for_support(shop.id)

    assert isinstance(context, ShopSupportContext)
    assert context.id == str(shop.id)
    assert context.status == "active"
    assert context.owner_user_id == str(shop.owner_user_id)


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("get_shop_for_support shop 不存在抛 404。")
@pytest.mark.asyncio
async def test_get_shop_for_support_missing_raises_404(
    shop_service: ShopService,
    mock_repository: AsyncMock,
) -> None:
    """shop 不存在时抛出 HTTP 404。"""
    mock_repository.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await shop_service.get_shop_for_support(uuid4())

    assert exc_info.value.status_code == 404


# ── validate_product_refs_for_shop ────────────────────────────


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("全部 product 属于 shop 时校验通过。")
@pytest.mark.asyncio
async def test_validate_refs_all_in_shop_passes(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """所有 id 存在且 shop_id 匹配时不抛异常。"""
    shop_id = str(uuid4())
    products = [_fake_product(shop_id=shop_id) for _ in range(2)]
    mock_product_repository.get_by_ids.return_value = products

    await shop_service.validate_product_refs_for_shop(
        shop_id, [p.id for p in products]
    )


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("任一 product 不存在时抛 422。")
@pytest.mark.asyncio
async def test_validate_refs_missing_product_raises_422(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """列表中含不存在的 product_id 时抛出 HTTP 422。"""
    shop_id = str(uuid4())
    existing = _fake_product(shop_id=shop_id)
    mock_product_repository.get_by_ids.return_value = [existing]

    with pytest.raises(HTTPException) as exc_info:
        await shop_service.validate_product_refs_for_shop(
            shop_id, [existing.id, str(uuid4())]
        )

    assert exc_info.value.status_code == 422


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("product 存在但跨 shop 时抛 422。")
@pytest.mark.asyncio
async def test_validate_refs_cross_shop_raises_422(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """product 存在但 shop_id 与参数不一致时抛出 HTTP 422。"""
    shop_id = str(uuid4())
    other_shop_product = _fake_product(shop_id=str(uuid4()))
    mock_product_repository.get_by_ids.return_value = [other_shop_product]

    with pytest.raises(HTTPException) as exc_info:
        await shop_service.validate_product_refs_for_shop(
            shop_id, [other_shop_product.id]
        )

    assert exc_info.value.status_code == 422


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("未上架本店 product 校验通过。")
@pytest.mark.asyncio
async def test_validate_refs_unpublished_allowed(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """product 属于该 shop 时即使未上架也不抛异常（不按公开可见性过滤）。"""
    shop_id = str(uuid4())
    product = _fake_product(shop_id=shop_id)
    mock_product_repository.get_by_ids.return_value = [product]

    await shop_service.validate_product_refs_for_shop(shop_id, [product.id])


@allure.epic("catalog")
@allure.feature("support_service")
@allure.title("空 product_ids 直接返回，不查询 repository。")
@pytest.mark.asyncio
async def test_validate_refs_empty_no_query(
    shop_service: ShopService,
    mock_product_repository: AsyncMock,
) -> None:
    """空列表输入不抛异常，且不触发 repository 查询。"""
    await shop_service.validate_product_refs_for_shop(str(uuid4()), [])

    mock_product_repository.get_by_ids.assert_not_awaited()
