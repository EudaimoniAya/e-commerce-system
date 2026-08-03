"""support 域 HTTP helper（原子单次 HTTP，返回 ``*Result``，不 assert 成功）。

仅依赖 httpx 与本层 results——不 import ``app.support``（红阶段尚未实现）。
"""

from httpx import AsyncClient, Response

from tests.support.results import (
    ConversationResult,
    InboxListResult,
    MessageListResult,
    MessageResult,
)


def _parse_body(response: Response) -> dict | None:
    """2xx 且非空响应时解析 JSON dict，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return response.json()
    return None


# ── 买家路径（Bearer JWT，get_current_user_id）──────────────────


async def get_buyer_conversation(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    shop_id: str,
) -> ConversationResult:
    """调用 GET /support/shops/{shop_id}/conversation，返回 ConversationResult。

    有会话 200；无会话 / shop 不存在 / 无权限 4xx。
    """
    response: Response = await client.get(
        f"/support/shops/{shop_id}/conversation",
        headers=headers,
    )
    return ConversationResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


async def post_buyer_message(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    shop_id: str,
    body: str | None = None,
    message_refs: list[dict[str, str]] | None = None,
) -> MessageResult:
    """调用 POST /support/shops/{shop_id}/conversation/messages，返回 MessageResult。

    ``body``/``message_refs`` 均省略时发送空对象 ``{}``（应触发 422）。
    首条消息 lazy create 会话；已有会话追加消息。
    """
    payload: dict[str, object] = {}
    if body is not None:
        payload["body"] = body
    if message_refs is not None:
        payload["message_refs"] = message_refs
    response: Response = await client.post(
        f"/support/shops/{shop_id}/conversation/messages",
        json=payload,
        headers=headers,
    )
    return MessageResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


async def list_buyer_messages(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    shop_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> MessageListResult:
    """调用 GET /support/shops/{shop_id}/conversation/messages，返回 MessageListResult。

    ``limit``/``offset`` 省略时由服务端默认（20 / 0）。无会话 → 404。
    """
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    response: Response = await client.get(
        f"/support/shops/{shop_id}/conversation/messages",
        params=params,
        headers=headers,
    )
    return MessageListResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


# ── 店主路径（get_current_shop）───────────────────────────────


async def list_inbox(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    limit: int | None = None,
    offset: int | None = None,
) -> InboxListResult:
    """调用 GET /support/inbox，返回 InboxListResult。

    ``limit``/``offset`` 省略时由服务端默认（20 / 0）。
    """
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    response: Response = await client.get(
        "/support/inbox",
        params=params,
        headers=headers,
    )
    return InboxListResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


async def get_inbox_conversation(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    conversation_id: str,
) -> ConversationResult:
    """调用 GET /support/inbox/{conversation_id}，返回 ConversationResult。

    非本店会话 → 404。
    """
    response: Response = await client.get(
        f"/support/inbox/{conversation_id}",
        headers=headers,
    )
    return ConversationResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


async def list_inbox_messages(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    conversation_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> MessageListResult:
    """调用 GET /support/inbox/{conversation_id}/messages，返回 MessageListResult。"""
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    response: Response = await client.get(
        f"/support/inbox/{conversation_id}/messages",
        params=params,
        headers=headers,
    )
    return MessageListResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )


async def post_shop_message(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    conversation_id: str,
    body: str | None = None,
    message_refs: list[dict[str, str]] | None = None,
) -> MessageResult:
    """调用 POST /support/inbox/{conversation_id}/messages，返回 MessageResult。

    店主回复；closed 店铺仍允许。
    """
    payload: dict[str, object] = {}
    if body is not None:
        payload["body"] = body
    if message_refs is not None:
        payload["message_refs"] = message_refs
    response: Response = await client.post(
        f"/support/inbox/{conversation_id}/messages",
        json=payload,
        headers=headers,
    )
    return MessageResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )
