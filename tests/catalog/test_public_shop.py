"""catalog 域 GET /shops/{shop_id} 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest

from tests.catalog.test_create_shop import _SHOP_FIELDS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_active_returns_200(client, shop_owner) -> None:
    """活跃店铺公开 GET 返回 200 与 status active。"""
    assert shop_owner["status_code"] == 201
    shop_id = shop_owner["json"]["id"]

    response = await client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= _SHOP_FIELDS
    assert body["id"] == shop_id
    assert body["status"] == "active"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_closed_returns_200(client, shop_owner) -> None:
    """已关闭店铺公开 GET 仍返回 200 与 status closed。"""
    assert shop_owner["status_code"] == 201
    shop_id = shop_owner["json"]["id"]

    patch_response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=shop_owner["headers"],
    )
    assert patch_response.status_code == 200

    response = await client.get(f"/shops/{shop_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == shop_id
    assert body["status"] == "closed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_public_shop_not_found_returns_404(client) -> None:
    """不存在的 shop_id 公开 GET 返回 404。"""
    missing_id = str(uuid.uuid4())

    response = await client.get(f"/shops/{missing_id}")

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body
