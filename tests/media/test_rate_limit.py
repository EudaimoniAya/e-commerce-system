"""media 域限速集成测试（TDD 红阶段）。

依赖 Redis 计数；超限返回 429。
"""

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext
from tests.support.helper.auth import auth_headers
from tests.support.helper.media import MINI_PNG_BYTES, upload_media


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("rate_limit")
@allure.title("同一用户超限制次上传返回 429")
async def test_rate_limit_exceeded_returns_429(
    integration_client: AsyncClient, authenticated_user: AuthContext
) -> None:
    """同一用户在限速窗口内超过允许次数后应返回 429。"""
    headers = auth_headers(authenticated_user.access_token)

    # 连续上传多次以触发限速（默认阈值应在 10–60 次区间）
    last_status = None
    for _ in range(100):
        result = await upload_media(
            integration_client,
            headers=headers,
            file_bytes=MINI_PNG_BYTES,
            filename="test.png",
        )
        last_status = result.status_code
        if last_status == 429:
            break

    assert last_status == 429, (
        f"预期多次请求后返回 429，但实际为 {last_status}"
    )
