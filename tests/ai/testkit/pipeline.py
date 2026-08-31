"""AI replies 集成测试共享装配：可编程 controller + dependency override 注入。

test-doubles 纪律：≥2 文件共用才进 testkit；数据载体（chunk/prompt）直接构造、不是替身。
注入点：``app.ai.deps.build_intent_controller``（router 以 ``Depends`` 消费，ADR-013
决策 1「将来有 AI router 时对同一函数使用 Depends」）。红阶段该函数尚未改名 → 导入即红。
"""

from collections.abc import Awaitable, Callable

from app.ai.agent.controller import IntentController
from app.ai.agent.registry import build_intent_registry
from app.ai.llm.client import FakeLLMClient, LLMClient
from app.ai.nlu.gateway import NLGateway

# NL 网关路由到 knowledge 且高置信（τ 阈值 0.3 之上）的固定输出
NLU_KNOWLEDGE_JSON = '{"intent": "knowledge", "confidence": 0.9}'


class FakePromptLoader:
    """dict 驱动的 prompt loader：``load(id)`` 返回 ``FakeLoadedPrompt``。"""

    def __init__(self, templates: dict[str, str]) -> None:
        self._templates = templates

    def load(self, prompt_id: str) -> "FakeLoadedPrompt":
        if prompt_id not in self._templates:
            raise KeyError(prompt_id)
        return FakeLoadedPrompt(text=self._templates[prompt_id])


class FakeLoadedPrompt:
    """数据载体：仅暴露 ``text``（不耦合 loader 实现）。"""

    def __init__(self, text: str) -> None:
        self.text = text


class FakeChunk:
    """数据载体：仅暴露 ``content_text``（对齐 KnowledgeHandler 消费字段）。"""

    def __init__(self, content_text: str) -> None:
        self.content_text = content_text


def spy_retrieve(
    records: list[dict],
    *,
    results: list[FakeChunk] | None = None,
) -> Callable[..., Awaitable[list]]:
    """记录调用的 spy retrieve；默认返回一个 chunk 供生成。"""

    async def _retrieve(
        shop_id: str, query: str, top_k: int = 5, product_id: str | None = None
    ) -> list:
        records.append(
            {
                "shop_id": shop_id,
                "query": query,
                "top_k": top_k,
                "product_id": product_id,
            }
        )
        return results if results is not None else [FakeChunk("默认 chunk")]

    return _retrieve


def build_controller(
    *,
    nlu_output: str,
    generation_output: str | None = None,
    records: list[dict] | None = None,
    retrieve_results: list[FakeChunk] | None = None,
    generation_llm: LLMClient | None = None,
    fallback_text: str = "转人工",
    tau_threshold: float = 0.3,
) -> IntentController:
    """装配可编程 controller：FakeLLMClient(NL) + spy retrieve + 生成 LLM。"""
    records = records if records is not None else []
    prompts = FakePromptLoader(
        {"nlu_route": "路由提示 {body}", "rag_answer": "依据 chunks 回答：{chunks}"}
    )
    gateway = NLGateway(llm=FakeLLMClient(nlu_output), prompt_loader=prompts)
    registry = build_intent_registry(
        retrieve=spy_retrieve(records, results=retrieve_results),
        generation_llm=generation_llm or FakeLLMClient(output=generation_output or ""),
        prompt_loader=prompts,
        fallback_text=fallback_text,
    )
    return IntentController(
        registry=registry,
        gateway=gateway,
        tau_threshold=tau_threshold,
        fallback_text=fallback_text,
    )


def override_intent_controller(controller: IntentController) -> None:
    """经 ``app.dependency_overrides`` 注入测试 controller。

    router SHALL 以 ``Depends(build_intent_controller)`` 消费（ADR-013 决策 1）；
    ``build_intent_controller`` 由 2.1 改名而来，红阶段导入即红。
    """
    from app.ai.deps import build_intent_controller
    from app.main import app

    app.dependency_overrides[build_intent_controller] = lambda: controller


def clear_intent_controller_override() -> None:
    """清理 build_intent_controller override（fixture teardown；导入缺失时容忍）。"""
    try:
        from app.ai.deps import build_intent_controller
        from app.main import app
    except ImportError:
        return
    app.dependency_overrides.pop(build_intent_controller, None)
