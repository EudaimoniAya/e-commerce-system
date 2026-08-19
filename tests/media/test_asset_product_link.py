"""media 域商品-文档关联 integration 测试（TDD 红阶段：MediaAsset.product_id 未实现）。

覆盖 spec media-storage「MediaAsset product association」：
- 上传商品文档且指定关联商品 → MediaAsset 行记录 product_id
- 非法 UUID 的 product_id 返回 4xx

红阶段红因：
- 测试 1：media 上传尚不支持 txt/PDF 文档（422 不支持文件类型）→ 断言 201 失败（红）
- 测试 2：上传 PNG（media 现有支持）+ 非法 product_id → 现有接口忽略该字段返回 201
  → 断言 4xx 失败（真红；驱动绿阶段 product_id 格式校验实现）
"""

import uuid

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.contexts import AuthContext
from tests.testkit.helper.media import MINI_PNG_BYTES
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("asset_product_link")
@allure.title("上传商品文档写入 product_id 关联")
async def test_upload_with_product_id_records_association(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    authenticated_user: AuthContext,
) -> None:
    """上传商品文档且指定关联商品 → media_assets 行记录 product_id。"""
    from app.media.models import MediaAsset

    product_id = str(uuid.uuid4())
    files = {"file": ("product-doc.txt", b"hello rag product document", "text/plain")}
    response = await integration_client.post(
        "/media",
        files=files,
        data={"product_id": product_id},
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code == 201, response.text
    media_id = response.json()["id"]

    row = await db_session.scalar(select(MediaAsset).where(MediaAsset.id == media_id))
    assert row is not None
    assert row.product_id == product_id


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("asset_product_link")
@allure.title("非法 product_id 格式返回 4xx")
async def test_upload_with_invalid_product_id_rejected(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """非法 UUID 格式的 product_id → 4xx 拒绝（spec：格式错误返回 4xx）。

    用 PNG（media 现有支持的图片）作载体：红阶段现有接口忽略 product_id 返回 201 → 断言 4xx 失败，
    驱动绿阶段 product_id 格式校验实现（而非「不支持 txt」的偶然 4xx）。
    """
    files = {"file": ("invalid-link.png", MINI_PNG_BYTES, "image/png")}
    response = await integration_client.post(
        "/media",
        files=files,
        data={"product_id": "not-a-valid-uuid"},
        headers=bearer_headers(authenticated_user.access_token),
    )

    assert response.status_code in (400, 422)
