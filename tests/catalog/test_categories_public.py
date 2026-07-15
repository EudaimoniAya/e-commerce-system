"""catalog 域 GET /categories 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import create_category, unique_category_name
from tests.catalog.test_admin_categories import _CATEGORY_FIELDS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_categories_returns_flat_list(
    client, admin_auth_headers
) -> None:
    """GET /categories 无需认证，返回扁平类目列表。"""
    assert admin_auth_headers["status_code"] == 200

    root_name = unique_category_name("list-root")
    root = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=root_name,
    )
    assert root["status_code"] == 201
    root_id = root["json"]["id"]

    child_name = unique_category_name("list-child")
    child = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=child_name,
        parent_id=root_id,
    )
    assert child["status_code"] == 201
    child_id = child["json"]["id"]

    response = await client.get("/categories")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)

    by_id = {item["id"]: item for item in body}
    assert root_id in by_id
    assert child_id in by_id
    assert set(by_id[root_id].keys()) >= _CATEGORY_FIELDS
    assert by_id[root_id]["name"] == root_name
    assert by_id[root_id]["parent_id"] is None
    assert by_id[child_id]["name"] == child_name
    assert by_id[child_id]["parent_id"] == root_id
    uuid.UUID(root_id)
    uuid.UUID(child_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_categories_empty_returns_200_and_empty_array(
    client, database_url: str
) -> None:
    """尚无类目记录时 GET /categories 返回 200 与空数组。"""
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # 红阶段 categories 表可能尚未创建，忽略清理失败
        for stmt in (
            "DELETE FROM product_categories",
            "DELETE FROM products",
            "DELETE FROM categories WHERE parent_id IS NOT NULL",
            "DELETE FROM categories",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass
    await engine.dispose()

    response = await client.get("/categories")

    assert response.status_code == 200
    assert response.json() == []
