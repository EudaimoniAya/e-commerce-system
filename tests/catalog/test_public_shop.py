"""catalog 域 GET /shops/{shop_id} 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import Response

from app.catalog.schemas import ShopResponse
from tests.support.contexts import ShopOwnerContext
from tests.support.projections import bearer_headers
from tests.support.results import RegisterResult, ShopResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_active_returns_200(
    client, shop_owner: ShopOwnerContext
) -> None:
    """活跃店铺公开 GET 返回 200 与 status active。"""
    shop_result = shop_owner.root.step(ShopResult)
    assert shop_result.status_code == 201
    assert shop_result.body is not None
    shop_id = shop_result.body.id

    response: Response = await client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.id == shop_id
    assert body.status == "active"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_closed_returns_200(
    client, shop_owner: ShopOwnerContext
) -> None:
    """已关闭店铺公开 GET 仍返回 200 与 status closed。"""
    shop_result = shop_owner.root.step(ShopResult)
    assert shop_result.status_code == 201
    assert shop_result.body is not None
    shop_id = shop_result.body.id

    patch_response: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
    )
    assert patch_response.status_code == 200

    response: Response = await client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = ShopResponse.model_validate(response.json())
    assert body.id == shop_id
    assert body.status == "closed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_not_found_returns_404(client) -> None:
    """不存在的 shop_id 公开 GET 返回 404。"""
    missing_id = str(uuid.uuid4())

    response: Response = await client.get(f"/shops/{missing_id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body
