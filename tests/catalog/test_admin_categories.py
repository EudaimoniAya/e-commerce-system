"""catalog 域 POST /categories integration 测试（TDD 红阶段）。"""

import uuid

import pytest

from tests.conftest import create_category, unique_category_name

_CATEGORY_FIELDS = {
    "id",
    "parent_id",
    "name",
    "created_at",
    "updated_at",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_root_category_success_returns_201(
    client, admin_auth_headers
) -> None:
    """管理员创建根类目成功，返回 201 与完整类目资料。"""
    assert admin_auth_headers["status_code"] == 200

    name = unique_category_name("root")
    result = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=name,
    )

    assert result["status_code"] == 201
    body = result["json"]
    assert body is not None
    assert set(body.keys()) >= _CATEGORY_FIELDS
    assert body["name"] == name
    assert body["parent_id"] is None
    uuid.UUID(body["id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_child_category_success_returns_201(
    client, admin_auth_headers
) -> None:
    """管理员在父类目下创建子类目成功，返回 201。"""
    assert admin_auth_headers["status_code"] == 200

    parent = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=unique_category_name("parent"),
    )
    assert parent["status_code"] == 201
    parent_id = parent["json"]["id"]

    child_name = unique_category_name("child")
    result = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=child_name,
        parent_id=parent_id,
    )

    assert result["status_code"] == 201
    body = result["json"]
    assert body is not None
    assert body["name"] == child_name
    assert body["parent_id"] == parent_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_category_duplicate_sibling_name_returns_422(
    client, admin_auth_headers
) -> None:
    """同一 parent_id 下类目名重复返回 422。"""
    assert admin_auth_headers["status_code"] == 200

    name = unique_category_name("dup")
    first = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=name,
    )
    assert first["status_code"] == 201

    second = await create_category(
        client,
        headers=admin_auth_headers["headers"],
        name=name,
    )

    assert second["status_code"] == 422
    body = second["json"]
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_category_non_admin_returns_403(
    client, authenticated_user
) -> None:
    """非管理员创建类目返回 403。"""
    assert authenticated_user["status_code"] == 201

    response = await client.post(
        "/categories",
        json={"name": unique_category_name("forbidden")},
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_category_unauthenticated_returns_401(client) -> None:
    """未携带 Bearer token 创建类目返回 401。"""
    response = await client.post(
        "/categories",
        json={"name": unique_category_name("anon")},
    )

    assert response.status_code == 401
