"""IntentController：NL 网关输出 → τ/意图门禁 → 注册 handler 或转人工兜底。"""

from __future__ import annotations

from app.ai.agent.registry import IntentRegistry
from app.ai.agent.tau import passed_tau
from app.ai.nlu.gateway import NLGateway


class IntentController:
    """客服回合编排：gateway 路由 → 仅 ``knowledge`` 且过 τ 才进注册 handler，否则兜底文案。"""

    def __init__(
        self,
        *,
        registry: IntentRegistry,
        gateway: NLGateway,
        tau_threshold: float,
        fallback_text: str,
    ) -> None:
        self._registry = registry
        self._gateway = gateway
        self._tau_threshold = tau_threshold
        self._fallback_text = fallback_text

    async def handle_buyer_turn(
        self,
        *,
        shop_id: str,
        body: str | None,
        product_ref_ids: list[str],
    ) -> str:
        """处理一轮买家输入：返回回复正文（或转人工兜底文案）。

        SHALL NOT 把未注册意图映射到 ``knowledge``；SHALL NOT 修改 ``handler_mode``。
        纯 ref 消息（``body=None``）归一为空串：仍进 NL 网关，空检索自然拒答。
        """
        body = body or ""
        decision = await self._gateway.route(body)
        if decision.intent != "knowledge" or not passed_tau(
            decision.confidence, self._tau_threshold
        ):
            return self._fallback_text
        handler = self._registry.get(decision.intent)
        if handler is None:
            return self._fallback_text
        return await handler.handle(
            shop_id=shop_id,
            body=body,
            product_ref_ids=product_ref_ids,
        )
