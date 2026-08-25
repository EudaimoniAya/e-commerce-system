"""NL 网关：读 ``nlu_route`` 提示词，经 LLM 产出 ``{intent, confidence}``。

路由判定（是否进入 knowledge handler）由 ``IntentController`` 执行；本类只负责
把 body 转成 ``NLDecision``。低于 τ / 集外意图由 controller 走转人工兜底。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.ai.llm.client import LLMClient
from app.ai.prompts.loader import PromptLoader


@dataclass(frozen=True)
class NLDecision:
    """NL 网关路由结果：``intent`` + ``[0,1]`` 置信度。"""

    intent: str
    confidence: float


class NLGateway:
    """将买家 body 路由为 ``NLDecision``（不直接判定 τ / 意图合法性）。"""

    def __init__(self, *, llm: LLMClient, prompt_loader: PromptLoader) -> None:
        self._llm = llm
        self._prompt_loader = prompt_loader

    async def route(self, body: str) -> NLDecision:
        """加载 ``nlu_route`` 提示词、填充 body、请求 LLM 并解析 JSON。"""
        prompt = self._prompt_loader.load("nlu_route")
        content = prompt.text.replace("{body}", body)
        raw = await self._llm.generate([{"role": "user", "content": content}])
        data = json.loads(raw)
        return NLDecision(
            intent=data["intent"],
            confidence=float(data["confidence"]),
        )
