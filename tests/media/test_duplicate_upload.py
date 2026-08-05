"""media 域重复上传集成测试：同字节两次 upload → 不同 id（TDD 红阶段）。"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("duplicate")
@allure.title("同字节两次 upload 产生不同 id（不去重）")
async def test_duplicate_upload_different_ids(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """相同字节上传两次应产生两条记录，且 id 不同（系统不去重）。"""
    headers = auth_headers(authenticated_user.access_token)

    first = await upload_media(
        integration_client,
        headers=headers,
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
        content_type="image/png",
    )
    assert first.status_code == 201
    assert first.body is not None

    second = await upload_media(
        integration_client,
        headers=headers,
        file_bytes=MINI_PNG_BYTES,
        filename="test.png",
        content_type="image/png",
    )
    assert second.status_code == 201
    assert second.body is not None

    # id 应不同（不去重）
    assert first.body["id"] != second.body["id"]

    # 两次的 url 格式应一致
    assert second.body["url"] == f"/media/{second.body['id']}/file"
    assert first.body["url"] == f"/media/{first.body['id']}/file"

    # 两次的 size_bytes 应相同
    assert first.body["size_bytes"] == len(MINI_PNG_BYTES)
    assert second.body["size_bytes"] == len(MINI_PNG_BYTES)
