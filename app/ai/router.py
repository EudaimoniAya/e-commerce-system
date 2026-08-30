"""AI 域客服 HTTP：``POST /ai/shops/{shop_id}/replies``（前端分流后的生成入口）。

流程（spec ai-http-replies / design Decision 1-2、5）：

1. 鉴权：infra ``get_current_user_id``（JWT ``sub``）；无会话 / 非该会话买家 → 404。
2. 读库组装一轮输入：``support.service.assemble_turn``（回看 query + product refs，
   AI 不穿透 support ORM）。
3. 分支：
   - 无非空买家正文、但回看到 product refs（纯卡片）→ **不进 NLU / 不检索**，落
     问候提示词 ``ask_about_product``。
   - 无非空正文且无 refs（前端误调）→ 落 ``suggest_human`` 兜底。
   - 有非空正文 → ``build_intent_controller().handle_buyer_turn(...)``；编排/LLM
     抛错仍 200，落 ``suggest_human``。
4. 落库：``support.service.append_ai_message``（``sender_role=shop`` /
   ``author_role=ai``），bump preview（截断 200）。

组合根契约（ADR-013 决策 1）：router 以 ``Depends(build_intent_controller)`` 消费
装配函数（测试经 ``app.dependency_overrides`` 注入）；support service-provider 经
``app.ai.deps`` 再导出（R5：AI 非组合根禁止直接 import 别域 deps）。
"""

import uuid

from fastapi import APIRouter, Depends

from app.ai.agent.controller import IntentController
from app.ai.deps import (
    build_intent_controller,
    build_prompt_loader,
    get_support_service,
)
from app.ai.schemas import AiReplyResponse
from app.infra.auth import get_current_user_id
from app.support.service import SupportService

router = APIRouter()


@router.post(
    "/ai/shops/{shop_id}/replies",
    response_model=AiReplyResponse,
    tags=["ai"],
)
async def post_ai_reply(
    shop_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SupportService = Depends(get_support_service),
    controller: IntentController = Depends(build_intent_controller),
) -> AiReplyResponse:
    """买家 AI 回复：读库组装一轮输入 → 问候/编排/兜底 → 落助手行，恒 200。

    未认证 401；无会话 404 且不建会话；成功与生成失败均为 200 并落 ``author_role=ai``
    助手行。请求 SHALL NOT 要求 JSON body。
    """
    turn = await service.assemble_turn(shop_id, user_id)
    loader = build_prompt_loader()

    if turn.query is None:
        # 纯卡片（仅 refs）→ 问候模板；无非空正文且无 refs → 转人工兜底（前端误调）。
        if turn.product_ref_ids:
            text = loader.load("ask_about_product").text
        else:
            text = loader.load("suggest_human").text
    else:
        try:
            text = await controller.handle_buyer_turn(
                shop_id=str(shop_id),
                body=turn.query,
                product_ref_ids=turn.product_ref_ids,
            )
        except Exception:
            # 生成/编排抛错：仍 200，落 suggest_human 兜底（不 5xx）。
            text = loader.load("suggest_human").text

    appended = await service.append_ai_message(shop_id, user_id, text)
    return AiReplyResponse(
        text=text,
        conversation_id=appended.conversation_id,
        assistant_message_id=appended.id,
    )
