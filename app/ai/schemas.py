"""ai 域 HTTP 请求/响应 DTO。

对齐 spec ai-http-replies：``POST /ai/shops/{shop_id}/replies`` 响应含
``text`` / ``conversation_id`` / ``assistant_message_id``，不用判别器
（``type: ai_answer | fallback_human``）。
"""

from __future__ import annotations

from pydantic import BaseModel


class AiReplyResponse(BaseModel):
    """AI 买家回复端点 200 响应：助手正文 + 会话/消息定位。"""

    text: str
    conversation_id: str
    assistant_message_id: str
