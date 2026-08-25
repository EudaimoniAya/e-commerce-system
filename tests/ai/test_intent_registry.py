"""意图注册表测试（TDD 红阶段）。

覆盖 spec ai-support-agent「Intent registry registers only knowledge」：
本 change 注册表仅包含 ``knowledge``，未注册意图不占位。
"""

import allure

from app.ai.agent.registry import build_intent_registry


async def _never_retrieve(
    shop_id: str, query: str, top_k: int = 5, product_id: str | None = None
) -> list:
    """本测试不应调用 retrieve；被调用即失败。"""
    raise AssertionError("本测试不应调用 retrieve")


class _NeverGenerationLLM:
    """本测试不应调用生成 LLM；被调用即失败。"""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        raise AssertionError("本测试不应调用生成 LLM")


class _NoPromptLoader:
    """本测试不应加载提示词；被调用即失败。"""

    def load(self, prompt_id: str) -> object:
        raise AssertionError("本测试不应加载提示词")


@allure.epic("ai")
@allure.feature("intent_registry")
@allure.title("注册表仅包含 knowledge。")
def test_registry_contains_only_knowledge() -> None:
    """本 change 的注册表已注册意图集合等于 {knowledge}。"""
    registry = build_intent_registry(
        retrieve=_never_retrieve,
        generation_llm=_NeverGenerationLLM(),
        prompt_loader=_NoPromptLoader(),
        fallback_text="转人工",
    )
    assert registry.names == frozenset({"knowledge"})


@allure.epic("ai")
@allure.feature("intent_registry")
@allure.title("注册表不包含 price / order 等未注册意图。")
def test_registry_does_not_contain_unregistered_intents() -> None:
    """未注册意图（价格 / 订单等）不占位，get 返回 None。"""
    registry = build_intent_registry(
        retrieve=_never_retrieve,
        generation_llm=_NeverGenerationLLM(),
        prompt_loader=_NoPromptLoader(),
        fallback_text="转人工",
    )
    assert "price" not in registry.names
    assert "order" not in registry.names
    assert registry.get("price") is None
