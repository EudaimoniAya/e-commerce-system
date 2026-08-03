"""support 域 GET /support/shops/{shop_id}/conversation integration 测试（TDD 红阶段）。

覆盖：404 无会话、200 有会话（必需字段）、shop 404、401 未认证、403 禁自购
（店主走买家路径访问本店会话）。
"""

import uuid

import allure
import pytest
from httpx import AsyncClient

from tests.support.contexts import AuthContext, ShopOwnerContext
from tests.support.helper.support import (
    get_buyer_conversation,
    post_buyer_message,
)
from tests.support.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_conversation")
@allure.title("认证买家对无会话 shop GET 返回 404。")
async def test_buyer_conversation_no_conversation_returns_404(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证买家对该 shop 尚无会话时 GET 返回 404。"""
    result = await get_buyer_conversation(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_conversation")
@allure.title("已有会话 GET 返回 200 且含必需字段。")
async def test_buyer_conversation_with_existing_returns_200(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家先发首条消息再 GET 会话：200 且含 id/shop_id/buyer_user_id/handler_mode/updated_at/last_message_preview。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201
    assert sent.body is not None

    result = await get_buyer_conversation(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert result.status_code == 200
    assert result.body is not None
    assert result.body["shop_id"] == shop_owner.shop_id
    assert result.body["buyer_user_id"] is not None
    assert result.body["handler_mode"] == "human"
    assert "id" in result.body
    assert "updated_at" in result.body
    assert "last_message_preview" in result.body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_conversation")
@allure.title("shop 不存在 GET 返回 404。")
async def test_buyer_conversation_shop_not_found_returns_404(
    integration_client: AsyncClient,
    authenticated_user: AuthContext,
) -> None:
    """请求的 shop_id 在 catalog 不存在时返回 404。"""
    fake_shop_id = str(uuid.uuid4())
    result = await get_buyer_conversation(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=fake_shop_id,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_conversation")
@allure.title("未认证 GET 返回 401。")
async def test_buyer_conversation_unauthenticated_returns_401(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证访问 GET /support/shops/{shop_id}/conversation 返回 401。"""
    result = await get_buyer_conversation(
        integration_client,
        headers={},
        shop_id=shop_owner.shop_id,
    )
    assert result.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_conversation")
@allure.title("店主走买家路径访问本店会话返回 403。")
async def test_buyer_conversation_owner_self_access_returns_403(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
) -> None:
    """该 shop 的 owner 走买家路径访问本店会话返回 403（禁自购延伸）。"""
    result = await get_buyer_conversation(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        shop_id=shop_owner.shop_id,
    )
    assert result.status_code == 403
