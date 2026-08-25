"""support 域店主 inbox integration 测试（TDD 红阶段）。

覆盖：inbox 本店隔离、updated_at DESC 排序、last_message_preview、店主回复 201、
closed 店店主仍可回复、非本店会话 404、无关用户访问 404。
"""

import asyncio

import allure
import pytest
from httpx import AsyncClient

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.auth import register_user_via_otp
from tests.testkit.helper.support import (
    get_buyer_conversation,
    get_inbox_conversation,
    list_buyer_messages,
    list_inbox,
    list_inbox_messages,
    post_buyer_message,
    post_shop_message,
)
from tests.testkit.utils import bearer_headers, decode_jwt_sub


async def _close_shop(integration_client: AsyncClient, token: str) -> None:
    """通过 PATCH /shops/me 将店铺状态置为 closed（店主身份）。"""
    response = await integration_client.patch(
        "/shops/me",
        json={"status": "closed"},
        headers=bearer_headers(token),
    )
    assert response.status_code == 200, response.text


async def _register_buyer_headers(integration_client: AsyncClient) -> dict[str, str]:
    """直接注册新买家并返回其 Bearer headers（等价于再要一个 authenticated_user）。"""
    registered = await register_user_via_otp(integration_client)
    assert registered.status_code == 201
    assert registered.body is not None
    return bearer_headers(registered.body.access_token)


async def _post_as_buyer(
    integration_client: AsyncClient,
    *,
    buyer_headers: dict[str, str],
    shop_id: str,
    body: str,
) -> dict:
    """买家发消息并断言 201，返回消息响应 dict。"""
    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_id,
        body=body,
    )
    assert sent.status_code == 201
    assert sent.body is not None
    return sent.body


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("inbox 仅含本店会话，并含 last_message_preview。")
async def test_inbox_isolated_by_shop_with_preview(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """同一买家向两 shop 发消息后，各店主 inbox 仅见本店会话。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    await _post_as_buyer(
        integration_client,
        buyer_headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="给A店",
    )
    await _post_as_buyer(
        integration_client,
        buyer_headers=buyer_headers,
        shop_id=second_shop_owner.shop_id,
        body="给B店",
    )

    shop_a_inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert shop_a_inbox.status_code == 200
    assert shop_a_inbox.body is not None
    assert all(
        item["shop_id"] == shop_owner.shop_id for item in shop_a_inbox.body["items"]
    )
    assert len(shop_a_inbox.body["items"]) == 1
    # 默认 handler_mode=ai：preview 为助手正文截断（本测试未注入 Port → 兜底文案，非空）
    assert shop_a_inbox.body["items"][0]["last_message_preview"]

    shop_b_inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(second_shop_owner.access_token),
    )
    assert shop_b_inbox.status_code == 200
    assert shop_b_inbox.body is not None
    assert all(
        item["shop_id"] == second_shop_owner.shop_id
        for item in shop_b_inbox.body["items"]
    )
    assert len(shop_b_inbox.body["items"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("买家发新消息后会话按 updated_at 升至 inbox 较前位置。")
async def test_inbox_ordered_by_updated_at_desc(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """两买家各有会话，买家一后续发消息 bump updated_at 后其会话位于 inbox 首位。"""
    buyer1_headers = bearer_headers(authenticated_user.access_token)
    buyer2_headers = await _register_buyer_headers(integration_client)
    buyer1_id = decode_jwt_sub(authenticated_user.access_token)

    await _post_as_buyer(
        integration_client,
        buyer_headers=buyer1_headers,
        shop_id=shop_owner.shop_id,
        body="买家一：第一条",
    )
    await _post_as_buyer(
        integration_client,
        buyer_headers=buyer2_headers,
        shop_id=shop_owner.shop_id,
        body="买家二：第一条",
    )

    # 确保时间戳秒级区分，再 bump 买家一会话到最新
    await asyncio.sleep(1.1)
    await _post_as_buyer(
        integration_client,
        buyer_headers=buyer1_headers,
        shop_id=shop_owner.shop_id,
        body="买家一：跟进",
    )

    inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert inbox.status_code == 200
    assert inbox.body is not None
    items = inbox.body["items"]
    assert len(items) == 2
    assert items[0]["buyer_user_id"] == buyer1_id
    assert [item["updated_at"] for item in items] == sorted(
        (item["updated_at"] for item in items), reverse=True
    )


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("店主回复成功：201 且 sender_role=shop、author_role=human。")
async def test_inbox_shop_reply_returns_201(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店主对属于本店的会话 POST 合法消息返回 201。"""
    await _post_as_buyer(
        integration_client,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body="请问有货吗",
    )
    inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert inbox.status_code == 200
    assert inbox.body is not None
    conversation_id = inbox.body["items"][0]["id"]

    reply = await post_shop_message(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        conversation_id=conversation_id,
        body="有货，欢迎下单",
    )

    assert reply.status_code == 201
    assert reply.body is not None
    assert reply.body["sender_role"] == "shop"
    assert reply.body["author_role"] == "human"

    messages = await list_buyer_messages(
        integration_client,
        headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
    )
    assert messages.status_code == 200
    assert messages.body is not None
    # 默认 ai：买家 POST 追加一条兜底助手行 → [买家, AI 兜底, 店主回复]
    assert len(messages.body["items"]) == 3


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("closed 店铺主仍可回复已有会话：201。")
async def test_inbox_shop_reply_after_close_returns_201(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店铺 closed 后店主仍可回复已有会话（售后收尾）。"""
    await _post_as_buyer(
        integration_client,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body="发货后我想退货",
    )
    await _close_shop(integration_client, shop_owner.access_token)

    inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert inbox.status_code == 200
    assert inbox.body is not None
    conversation_id = inbox.body["items"][0]["id"]

    reply = await post_shop_message(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
        conversation_id=conversation_id,
        body="已为您登记售后",
    )

    assert reply.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("非本店会话 GET 返回 404。")
async def test_inbox_other_shop_conversation_returns_404(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """店主请求不属于本店的 conversation_id 返回 404。"""
    await _post_as_buyer(
        integration_client,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body="给A店",
    )
    inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert inbox.status_code == 200
    assert inbox.body is not None
    conversation_id = inbox.body["items"][0]["id"]

    other_shop_headers = bearer_headers(second_shop_owner.access_token)
    detail = await get_inbox_conversation(
        integration_client,
        headers=other_shop_headers,
        conversation_id=conversation_id,
    )
    assert detail.status_code == 404

    messages = await list_inbox_messages(
        integration_client,
        headers=other_shop_headers,
        conversation_id=conversation_id,
    )
    assert messages.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("inbox")
@allure.title("无关用户访问买家/店主会话路径返回 404。")
async def test_inbox_unrelated_user_returns_404(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """既非会话 buyer 也非 shop 店主的认证用户访问任一会话路径返回 404。"""
    await _post_as_buyer(
        integration_client,
        buyer_headers=bearer_headers(authenticated_user.access_token),
        shop_id=shop_owner.shop_id,
        body="咨询商品",
    )
    inbox = await list_inbox(
        integration_client,
        headers=bearer_headers(shop_owner.access_token),
    )
    assert inbox.status_code == 200
    assert inbox.body is not None
    conversation_id = inbox.body["items"][0]["id"]

    stranger_headers = await _register_buyer_headers(integration_client)
    buyer_conv = await get_buyer_conversation(
        integration_client,
        headers=stranger_headers,
        shop_id=shop_owner.shop_id,
    )
    assert buyer_conv.status_code == 404

    inbox_detail = await get_inbox_conversation(
        integration_client,
        headers=stranger_headers,
        conversation_id=conversation_id,
    )
    assert inbox_detail.status_code == 404

    inbox_messages = await list_inbox_messages(
        integration_client,
        headers=stranger_headers,
        conversation_id=conversation_id,
    )
    assert inbox_messages.status_code == 404
