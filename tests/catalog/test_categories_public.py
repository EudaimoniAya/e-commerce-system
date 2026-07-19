"""catalog 域 GET /categories 公开端点 integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.schemas import CategoryResponse
from tests.support.helpers import create_category
from tests.support.builders import unique_category_name
from tests.support.contexts import AdminAuthContext
from tests.support.projections import bearer_headers
from tests.support.results import CategoryResult, LoginResult


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_categories_returns_flat_list(
    client, admin_auth_headers: AdminAuthContext
) -> None:
    """GET /categories 无需认证，返回扁平类目列表。"""
    admin_headers = bearer_headers(admin_auth_headers.root.step(LoginResult))
    assert admin_auth_headers.root.step(LoginResult).status_code == 200

    root_name = unique_category_name("list-root")
    root: CategoryResult = await create_category(
        client,
        headers=admin_headers,
        name=root_name,
    )
    assert root.status_code == 201
    assert root.body is not None
    root_id = root.body.id

    child_name = unique_category_name("list-child")
    child: CategoryResult = await create_category(
        client,
        headers=admin_headers,
        name=child_name,
        parent_id=root_id,
    )
    assert child.status_code == 201
    assert child.body is not None
    child_id = child.body.id

    response: Response = await client.get("/categories")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)

    by_id: dict[str, CategoryResponse] = {}
    for item in body:
        category = CategoryResponse.model_validate(item)
        by_id[category.id] = category
    assert root_id in by_id
    assert child_id in by_id
    assert by_id[root_id].name == root_name
    assert by_id[root_id].parent_id is None
    assert by_id[child_id].name == child_name
    assert by_id[child_id].parent_id == root_id
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

    response: Response = await client.get("/categories")

    assert response.status_code == 200
    assert response.json() == []
