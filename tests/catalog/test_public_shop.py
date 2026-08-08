"""catalog 域 GET /shops/{shop_id} 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import allure
import pytest
from httpx import AsyncClient, Response

from app.catalog.schemas import ShopResponse
from tests.testkit.contexts import ShopOwnerContext
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_shop")
@allure.title("活跃店铺公开 GET 返回 200 与 status active")
async def test_get_public_shop_active_returns_200(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """活跃店铺公开 GET 返回 200 与 status active。"""
    shop_id = shop_owner.shop_id

    response: Response = await integration_client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.id == shop_id
    assert body.status == "active"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_shop")
@allure.title("已关闭店铺公开 GET 仍返回 200 与 status closed")
async def test_get_public_shop_closed_returns_200(
    integration_client: AsyncClient, shop_owner: ShopOwnerContext
) -> None:
    """已关闭店铺公开 GET 仍返回 200 与 status closed。"""
    shop_id = shop_owner.shop_id

    patch_response: Response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(shop_owner.access_token),
    )
    assert patch_response.status_code == 200

    response: Response = await integration_client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.id == shop_id
    assert body.status == "closed"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("public_shop")
@allure.title("不存在的 shop_id 公开 GET 返回 404")
async def test_get_public_shop_not_found_returns_404(
    integration_client: AsyncClient,
) -> None:
    """不存在的 shop_id 公开 GET 返回 404。"""
    missing_id = str(uuid.uuid4())

    response: Response = await integration_client.get(f"/shops/{missing_id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "error" in body
