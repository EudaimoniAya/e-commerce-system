"""catalog 域 POST /products integration 测试（TDD 红阶段）。"""

import uuid

import pytest
from httpx import Response

from app.catalog.schemas import ProductResponse
from tests.support.helpers import create_category
from tests.support.builders import build_product_create, unique_category_name
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import CategoryResult, LoginResult, RegisterResult, ShopResult


def _owner_pipeline(owner: ShopOwnerContext | PipelineResult) -> PipelineResult:
    """统一从 fixture Context 或 orchestrator Pipeline 取 PipelineResult。"""
    if isinstance(owner, ShopOwnerContext):
        return owner.root
    return owner


async def _create_category_for_product(
    client, admin_auth_headers: AdminAuthContext
) -> str:
    """管理员创建测试用类目，返回 category id。"""
    login = admin_auth_headers.root.step(LoginResult)
    assert login.status_code == 200
    result: CategoryResult = await create_category(
        client,
        headers=bearer_headers(login),
        name=unique_category_name("product"),
    )
    assert result.status_code == 201
    assert result.body is not None
    return result.body.id


async def _create_product(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext | PipelineResult,
    *,
    is_published: bool = False,
    category_id: str | None = None,
) -> ProductResponse:
    """店主创建商品并返回 ProductResponse。"""
    if category_id is None:
        category_id = await _create_category_for_product(client, admin_auth_headers)
    product_request = build_product_create(
        category_ids=[category_id],
        primary_category_id=category_id,
        is_published=is_published,
    )
    pipeline = _owner_pipeline(shop_owner)
    response: Response = await client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(pipeline.step(RegisterResult)),
    )
    assert response.status_code == 201
    return ProductResponse.model_validate(response.json())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_success_returns_201(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店主在 active 店铺下创建商品成功，返回 201 与 ProductResponse。"""
    shop_result = shop_owner.root.step(ShopResult)
    assert shop_result.status_code == 201
    assert shop_result.body is not None

    category_id = await _create_category_for_product(client, admin_auth_headers)
    product_request = build_product_create(
        description="测试商品简介",
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response: Response = await client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner.root.step(RegisterResult)),
    )

    assert response.status_code == 201
    body = ProductResponse.model_validate(response.json())
    assert body.name == product_request.name
    assert body.description == product_request.description
    assert body.price == str(product_request.price)
    assert body.stock == product_request.stock
    assert body.is_published is False
    assert body.shop_id == shop_result.body.id
    uuid.UUID(body.id)

    assert len(body.categories) >= 1
    primary = next(c for c in body.categories if c.is_primary)
    assert primary.id == category_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_closed_shop_returns_422(
    client,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """店铺 status 为 closed 时 POST /products 返回 422。"""
    assert shop_owner.root.step(ShopResult).status_code == 201
    owner_headers = bearer_headers(shop_owner.root.step(RegisterResult))

    patch_response: Response = await client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert patch_response.status_code == 200

    category_id = await _create_category_for_product(client, admin_auth_headers)
    product_request = build_product_create(
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response: Response = await client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=owner_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body is not None
    assert "detail" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_product_no_shop_returns_404(
    client,
    admin_auth_headers: AdminAuthContext,
    authenticated_user: AuthContext,
) -> None:
    """已认证但无店铺的用户 POST /products 返回 404。"""
    registered = authenticated_user.root.step(RegisterResult)
    assert registered.status_code == 201

    category_id = await _create_category_for_product(client, admin_auth_headers)
    product_request = build_product_create(
        category_ids=[category_id],
        primary_category_id=category_id,
    )

    response: Response = await client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(registered),
    )

    assert response.status_code == 404
    body = response.json()
    assert body is not None
    assert "detail" in body
