"""ai 域 HTTP helper（原子单次 HTTP，返回 ``*Result``，不 assert 成功）。

仅依赖 httpx 与本层 results——不 import ``app.ai``（红阶段尚未实现）。
"""

from httpx import AsyncClient, Response

from tests.testkit.results import AiReplyResult


def _parse_body(response: Response) -> dict | None:
    """2xx 且非空响应时解析 JSON dict，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return response.json()
    return None


async def post_ai_reply(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    shop_id: str,
) -> AiReplyResult:
    """调用 ``POST /ai/shops/{shop_id}/replies``（无请求 body），返回 AiReplyResult。

    未认证 → 401；认证买家对该 shop 无会话 → 404（不建会话）；
    有会话 → 200（text/conversation_id/assistant_message_id）。
    """
    response: Response = await client.post(
        f"/ai/shops/{shop_id}/replies",
        headers=headers,
    )
    return AiReplyResult(
        status_code=response.status_code,
        body=_parse_body(response),
    )
