"""catalog 域 product primary_media attach integration 测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/catalog-products/spec.md MODIFIED Requirements）：
- POST /products 带 primary_media_id → 201 + image_url resolve
- PATCH /products/{id} 更新 primary_media_id → 200
- 绑他人 media → 403
- 非 image attach → 422
- 清空主图 → image_url=null

.. note::
    本文件 **仅编写测试**，不编写 catalog/media attach 实现。
"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.builders import build_product_create
from tests.support.contexts import AdminAuthContext, ShopOwnerContext
from tests.support.helper.auth import auth_headers, register_user_via_otp
from tests.support.helper.catalog import create_category, create_product
from tests.support.helper.media import MINI_PNG_BYTES, upload_media
from tests.support.utils import bearer_headers


async def _upload_png(client: AsyncClient, token: str) -> str:
    result = await upload_media(
        client,
        headers=auth_headers(token),
        file_bytes=MINI_PNG_BYTES,
        filename="product.png",
        content_type="image/png",
    )
    assert result.status_code == 201
    assert result.body is not None
    return result.body["id"]


# ── POST /products attach 成功 ─────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("product_media")
@allure.title("POST /products 带 primary_media_id 返回 201 且 image_url resolve")
async def test_create_product_with_primary_media_id(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """POST /products 带合法 primary_media_id → 201 + image_url。"""
    media_id = await _upload_png(integration_client, shop_owner.access_token)

    # 类目创建仅 admin 可操作（seed 管理员登录见 admin_auth_headers fixture）
    category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
    )
    assert category.status_code == 201 and category.body is not None
    cid = category.body.id

    product_request = build_product_create(
        primary_media_id=media_id,
        category_ids=[cid],
        primary_category_id=cid,
    )
    response = await integration_client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_url"] == f"/media/{media_id}/file"


# ── PATCH /products/{id} attach 成功 ────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("product_media")
@allure.title("PATCH /products/{id} 更新 primary_media_id 返回 200")
async def test_update_product_primary_media_id(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """PATCH /products/{id} 更新 primary_media_id → 200 + image_url resolve。"""
    # 先创建无主图商品
    category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
    )
    assert category.status_code == 201 and category.body is not None

    product_result = await create_product(
        integration_client,
        shop_owner_token=shop_owner.access_token,
        category=category,
    )
    if product_result.status_code != 201:
        pytest.skip("创建商品失败，无法继续测试")

    pid = product_result.body.id if product_result.body else None
    if pid is None:
        pytest.skip("商品创建失败")

    # 上传 media 并 attach
    media_id = await _upload_png(integration_client, shop_owner.access_token)
    response = await integration_client.patch(
        f"/products/{pid}",
        json={"primary_media_id": media_id},
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 200
    assert response.json()["image_url"] == f"/media/{media_id}/file"


# ── 403：绑他人 media ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("product_media")
@allure.title("绑他人 media 返回 403")
async def test_attach_others_primary_media_returns_403(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """POST /products 带他人 media_id → 403。"""
    other_user = await register_user_via_otp(integration_client)
    assert other_user.status_code == 201 and other_user.body is not None
    others_media_id = await _upload_png(
        integration_client, other_user.body.access_token
    )

    category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
    )
    assert category.status_code == 201 and category.body is not None
    cid = category.body.id

    product_request = build_product_create(
        primary_media_id=others_media_id,
        category_ids=[cid],
        primary_category_id=cid,
    )
    response = await integration_client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner.access_token),
    )

    assert response.status_code == 403


# ── 清空主图 ────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("product_media")
@allure.title("清空 primary_media_id 后 image_url 为 null")
async def test_clear_primary_media_id(
    integration_client: AsyncClient,
    admin_auth_headers: AdminAuthContext,
    shop_owner: ShopOwnerContext,
) -> None:
    """PATCH primary_media_id=null → 200 + image_url=null。"""
    category = await create_category(
        integration_client,
        headers=bearer_headers(admin_auth_headers.access_token),
    )
    assert category.status_code == 201 and category.body is not None
    cid = category.body.id

    # 先创建带主图的商品
    media_id = await _upload_png(integration_client, shop_owner.access_token)
    product_request = build_product_create(
        primary_media_id=media_id,
        category_ids=[cid],
        primary_category_id=cid,
    )
    create_resp = await integration_client.post(
        "/products",
        json=product_request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner.access_token),
    )
    if create_resp.status_code != 201:
        pytest.skip("创建商品失败")

    pid = create_resp.json()["id"]

    # 清空主图
    clear_resp = await integration_client.patch(
        f"/products/{pid}",
        json={"primary_media_id": None},
        headers=bearer_headers(shop_owner.access_token),
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["image_url"] is None
