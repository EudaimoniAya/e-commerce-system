"""support 域买家 PATCH handler_mode integration 测试（TDD 红阶段）。

覆盖 spec support-conversations「Buyer PATCH handler_mode」与「AI port on buyer
POST when mode is ai」的**模式门禁**子集（不注入 Port）：
- PATCH human / ai 返回 200
- 无会话 404、非法值 422、未认证 401
- ``handler_mode=human`` 时买家 POST 不新增 ``author_role=ai`` 行
- 店主 inbox POST 不触发 AI 行

**不编写** PATCH 路由与 Port（红阶段，PATCH 路由缺失 → 405 即红）。
"""

import allure
import pytest
from httpx import AsyncClient

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.support import (
    list_buyer_messages,
    patch_buyer_handler_mode,
    post_buyer_message,
    post_shop_message,
)
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("买家 PATCH handler_mode=human 返回 200 且会话切为 human。")
async def test_patch_handler_mode_human_returns_200(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """已有会话时 PATCH human → 200，响应体 handler_mode=human。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201

    patched = await patch_buyer_handler_mode(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        handler_mode="human",
    )

    assert patched.status_code == 200
    assert patched.body is not None
    assert patched.body["handler_mode"] == "human"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("买家 PATCH handler_mode=ai 返回 200 且会话切为 ai。")
async def test_patch_handler_mode_ai_returns_200(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """已有会话时 PATCH ai → 200，响应体 handler_mode=ai。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201

    patched = await patch_buyer_handler_mode(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        handler_mode="ai",
    )

    assert patched.status_code == 200
    assert patched.body is not None
    assert patched.body["handler_mode"] == "ai"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("无会话 PATCH 返回 404。")
async def test_patch_handler_mode_no_conversation_returns_404(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证买家对该 shop 尚无会话时 PATCH 返回 404。"""
    result = await patch_buyer_handler_mode(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        handler_mode="human",
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("非法 handler_mode 返回 422。")
async def test_patch_handler_mode_invalid_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """PATCH 的 handler_mode 既非 ai 也非 human 时返回 422。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201

    result = await patch_buyer_handler_mode(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        handler_mode="robot",
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("未认证 PATCH 返回 401。")
async def test_patch_handler_mode_unauthenticated_returns_401(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
) -> None:
    """未认证访问 PATCH 返回 401。"""
    result = await patch_buyer_handler_mode(
        integration_client,
        headers={},
        shop_id=shop_owner.shop_id,
        handler_mode="human",
    )
    assert result.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("handler_mode=human 时买家 POST 不新增 author_role=ai 行。")
async def test_human_mode_post_does_not_add_ai_message(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """切到 human 后买家 POST 只新增买家行，不写 author_role=ai。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    first = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert first.status_code == 201

    before = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert before.status_code == 200
    assert before.body is not None

    patched = await patch_buyer_handler_mode(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        handler_mode="human",
    )
    assert patched.status_code == 200

    second = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="人工提问",
    )
    assert second.status_code == 201

    after = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert after.status_code == 200
    assert after.body is not None
    items = after.body["items"]
    assert len(items) == len(before.body["items"]) + 1
    assert items[-1]["author_role"] == "human"
    assert items[-1]["sender_role"] == "buyer"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("默认 ai 窗口下买家 POST 不新增 author_role=ai 行。")
async def test_ai_mode_post_does_not_add_ai_message(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """handler_mode=ai（默认）时买家 POST 只落买家行，不自动追加 ai 助手行。

    BREAKING（本 change）：入口改为前端分流，买家 POST 不再读 handler_mode 调 AI。
    """
    buyer_headers = bearer_headers(authenticated_user.access_token)
    first = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert first.status_code == 201

    second = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="再问一句",
    )
    assert second.status_code == 201

    after = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert after.status_code == 200
    assert after.body is not None
    items = after.body["items"]
    assert len(items) == 2
    assert all(item["author_role"] == "human" for item in items)
    assert all(item["sender_role"] == "buyer" for item in items)


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("handler_mode")
@allure.title("AI 模式下店主 inbox POST 不触发 AI 行。")
async def test_shop_inbox_post_does_not_trigger_ai(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """会话默认 ai 时，店主 inbox POST 只新增店主人工行，不因该 POST 新增第二条 author_role=ai。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    first = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert first.status_code == 201
    assert first.body is not None
    conversation_id = first.body["conversation_id"]

    before = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert before.status_code == 200
    assert before.body is not None

    replied = await post_shop_message(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        conversation_id=conversation_id,
        body="人工回复",
    )
    assert replied.status_code == 201

    after = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert after.status_code == 200
    assert after.body is not None
    items = after.body["items"]
    assert len(items) == len(before.body["items"]) + 1
    assert items[-1]["author_role"] == "human"
    assert items[-1]["sender_role"] == "shop"
