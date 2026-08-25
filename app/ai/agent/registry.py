"""意图注册表：每 agent 一份；本 change 仅注册 ``knowledge``（无空占位）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.ai.agent.handlers import KnowledgeHandler
from app.ai.llm.client import LLMClient
from app.ai.prompts.loader import PromptLoader


class IntentHandler(Protocol):
    """注册意图的处理器契约（本 change 由 ``KnowledgeHandler`` 实现）。"""

    async def handle(
        self,
        *,
        shop_id: str,
        body: str,
        product_ref_ids: list[str],
    ) -> str:
        """消费一轮买家输入，返回回复正文。"""


class IntentRegistry:
    """按意图名登记 handler；``names`` 暴露已注册集合。"""

    def __init__(self) -> None:
        self._handlers: dict[str, IntentHandler] = {}

    def register(self, name: str, handler: IntentHandler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> IntentHandler | None:
        return self._handlers.get(name)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)


def build_intent_registry(
    *,
    retrieve: Callable[..., Awaitable[list]],
    generation_llm: LLMClient,
    prompt_loader: PromptLoader,
    fallback_text: str,
) -> IntentRegistry:
    """装配本 change 的注册表：**仅**注册 ``knowledge``，未注册意图不占位。"""
    registry = IntentRegistry()
    registry.register(
        "knowledge",
        KnowledgeHandler(
            retrieve=retrieve,
            generation_llm=generation_llm,
            prompt_loader=prompt_loader,
            fallback_text=fallback_text,
        ),
    )
    return registry
