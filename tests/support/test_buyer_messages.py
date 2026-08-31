"""support 域买家 POST / GET 消息 integration 测试（TDD 红阶段）。

覆盖：POST lazy create 201、同 shop 复用会话、GET messages ASC / 无会话 404、
closed 店买家 POST 422、body 与 refs 皆空 422、body 超长 422。
"""

import allure
import pytest
from httpx import AsyncClient

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.support import (
    get_buyer_conversation,
    list_buyer_messages,
    post_buyer_message,
)
from tests.testkit.utils import bearer_headers


async def _close_shop(integration_client: AsyncClient, token: str) -> None:
    """通过 PATCH /shops/me 将店铺状态置为 closed（店主身份）。"""
    response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(token),
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("买家对 active shop 首条消息 lazy create 返回 201。")
async def test_buyer_message_lazy_create_returns_201(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """首条消息 201，sender_role=buyer，并创建唯一 (shop_id, buyer_user_id) 会话。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)

    result = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="我想咨询一下",
    )

    assert result.status_code == 201
    assert result.body is not None
    assert result.body["sender_role"] == "buyer"
    assert result.body["author_role"] == "human"
    assert result.body["conversation_id"] is not None
    assert result.body["body"] == "我想咨询一下"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("同 shop 再次 POST 复用同一会话，不重复创建。")
async def test_buyer_message_reuses_conversation(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """第二次 POST 追加消息，conversation_id 与首条一致（仅一个会话）。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)

    first = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="第一条",
    )
    assert first.status_code == 201
    assert first.body is not None

    second = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="第二条",
    )

    assert second.status_code == 201
    assert second.body is not None
    assert second.body["conversation_id"] == first.body["conversation_id"]

    conversation = await get_buyer_conversation(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert conversation.status_code == 200
    assert conversation.body is not None
    assert conversation.body["id"] == first.body["conversation_id"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("GET messages 按 created_at 升序返回全部消息。")
async def test_buyer_messages_list_ascending(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """多消息后 GET messages：items 升序，且每条含 sender_role/author_role/body/message_refs。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    for text in ("第一", "第二", "第三"):
        sent = await post_buyer_message(
            integration_client,
            headers=buyer_headers,
            shop_id=shop_owner.shop_id,
            body=text,
        )
        assert sent.status_code == 201

    result = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert result.status_code == 200
    assert result.body is not None
    items = result.body["items"]
    # 买家 POST 只落买家行（本 change 不再自动追加 ai 行）→ 无任何 author_role=ai 行
    assert len(items) == 3
    assert all(item["author_role"] != "ai" for item in items)
    buyer_bodies = [item["body"] for item in items if item["sender_role"] == "buyer"]
    assert buyer_bodies == ["第一", "第二", "第三"]
    assert [item["created_at"] for item in items] == sorted(
        item["created_at"] for item in items
    )
    for item in items:
        assert "sender_role" in item
        assert "author_role" in item
        assert "body" in item
        assert "message_refs" in item


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("无会话 GET messages 返回 404。")
async def test_buyer_messages_no_conversation_returns_404(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证买家对该 shop 尚无会话时 GET messages 返回 404。"""
    result = await list_buyer_messages(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
    )
    assert result.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("closed 店买家 POST 返回 422。")
async def test_buyer_message_closed_shop_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """对 status=closed 的 shop POST 消息返回 422。"""
    await _close_shop(integration_client, shop_owner.access_token)

    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body="还能咨询吗",
    )

    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("body 与 refs 皆空返回 422。")
async def test_buyer_message_empty_body_and_refs_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """POST 且 body 缺失/空、message_refs 缺失/空时返回 422。"""
    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
    )
    assert result.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("buyer_messages")
@allure.title("body 超过 2000 字符返回 422。")
async def test_buyer_message_body_too_long_returns_422(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """body 长度超过 2000 时返回 422。"""
    too_long = "x" * 2001
    result = await post_buyer_message(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body=too_long,
    )
    assert result.status_code == 422
