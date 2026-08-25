"""IntentController 路由测试（TDD 红阶段）。

覆盖 spec ai-support-agent：
- NL 网关按 intent 与 τ 路由：unknown / 低置信 → 不调用 retrieve，返回兜底文案
- 知识检索按 message refs 计算 ``product_id``：0 → None、1 → 该 id、多 → 最后一个
- 空检索不调用生成 LLM，返回兜底文案

依赖全部注入（fake LLM / fake prompt loader / fake retrieve / fake 生成 LLM），
不编写 agent / loader 实现。
"""

import json
from collections.abc import Awaitable, Callable

import allure
import pytest

from app.ai.agent.controller import IntentController
from app.ai.agent.registry import build_intent_registry
from app.ai.nlu.gateway import NLGateway


class _FakeLLM:
    """可编程 LLM：返回固定 JSON 正文（``{intent, confidence}``）。"""

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self._output


class _FakeLoadedPrompt:
    """假 LoadedPrompt：仅暴露 ``text``（控制器测试不耦合 loader 实现）。"""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakePromptLoader:
    """dict 驱动的假 prompt loader：``load(id)`` 返回模板。"""

    def __init__(self, templates: dict[str, str]) -> None:
        self._templates = templates

    def load(self, prompt_id: str) -> _FakeLoadedPrompt:
        if prompt_id not in self._templates:
            raise KeyError(prompt_id)
        return _FakeLoadedPrompt(text=self._templates[prompt_id])


class _FakeChunk:
    """假 RetrievedChunk：仅暴露 ``content_text``。"""

    def __init__(self, content_text: str) -> None:
        self.content_text = content_text


class _FakeGenerationLLM:
    """记录调用的生成 LLM。"""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.reply = "生成答案"

    async def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.reply


def _make_retrieve(
    records: list[dict],
    *,
    results: list[_FakeChunk] | None = None,
) -> Callable[..., Awaitable[list]]:
    """记录调用的 fake retrieve；默认返回一个 chunk 供生成。"""

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
        return results if results is not None else [_FakeChunk("默认 chunk")]

    return _retrieve


def _build_pipeline(
    *,
    llm_output: str,
    records: list[dict],
    gen_llm: _FakeGenerationLLM | None = None,
    retrieve_results: list[_FakeChunk] | None = None,
) -> IntentController:
    """装配可编程 pipeline：fake LLM + fake prompt loader + fake retrieve + 生成 LLM。"""
    prompts = _FakePromptLoader(
        {
            "nlu_route": "路由提示 {body}",
            "rag_answer": "依据 chunks 回答：{chunks}",
        }
    )
    gateway = NLGateway(llm=_FakeLLM(llm_output), prompt_loader=prompts)
    registry = build_intent_registry(
        retrieve=_make_retrieve(records, results=retrieve_results),
        generation_llm=gen_llm or _FakeGenerationLLM(),
        prompt_loader=prompts,
        fallback_text="转人工",
    )
    return IntentController(
        registry=registry,
        gateway=gateway,
        tau_threshold=0.3,
        fallback_text="转人工",
    )


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("Mock LLM 输出 unknown 意图时不调用 retrieve，返回兜底文案。")
async def test_unknown_intent_does_not_call_retrieve() -> None:
    """意图集外（unknown）→ 转人工兜底，不检索、不生成。"""
    records: list[dict] = []
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "unknown", "confidence": 0.9}),
        records=records,
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="多少钱", product_ref_ids=[]
    )

    assert text == "转人工"
    assert records == []


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("knowledge 但置信度低于 τ 时不调用 retrieve，返回兜底文案。")
async def test_low_confidence_does_not_call_retrieve() -> None:
    """intent=knowledge 但 confidence < τ → 视为未达 τ，不检索。"""
    records: list[dict] = []
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "knowledge", "confidence": 0.1}),
        records=records,
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="有货吗", product_ref_ids=[]
    )

    assert text == "转人工"
    assert records == []


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("knowledge+高置信、无 ref → retrieve 的 product_id 为 None。")
async def test_knowledge_high_conf_no_refs_passes_none() -> None:
    """0 个 product ref → 整店检索（product_id=None）。"""
    records: list[dict] = []
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "knowledge", "confidence": 0.9}),
        records=records,
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="这款包怎么样", product_ref_ids=[]
    )

    assert text == "生成答案"
    assert len(records) == 1
    assert records[0]["shop_id"] == "s1"
    assert records[0]["query"] == "这款包怎么样"
    assert records[0]["product_id"] is None


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("knowledge+高置信、单个 ref → retrieve 的 product_id 为该 ref。")
async def test_knowledge_high_conf_single_ref_passes_ref_id() -> None:
    """1 个 product ref → 按该商品过滤。"""
    records: list[dict] = []
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "knowledge", "confidence": 0.9}),
        records=records,
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="这款包", product_ref_ids=["p1"]
    )

    assert text == "生成答案"
    assert len(records) == 1
    assert records[0]["product_id"] == "p1"


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("knowledge+高置信、多个 ref → retrieve 的 product_id 为最后一个。")
async def test_knowledge_high_conf_multi_refs_pass_last() -> None:
    """≥2 个 product ref → 取去重后最后一项。"""
    records: list[dict] = []
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "knowledge", "confidence": 0.9}),
        records=records,
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="看看", product_ref_ids=["p1", "p2", "p3"]
    )

    assert text == "生成答案"
    assert len(records) == 1
    assert records[0]["product_id"] == "p3"


@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("intent_controller")
@allure.title("空检索不调用生成 LLM，返回兜底文案。")
async def test_empty_retrieval_does_not_call_generation_llm() -> None:
    """retrieve 返回空列表 → 不调生成 LLM，拒答/转人工文案。"""
    records: list[dict] = []
    gen_llm = _FakeGenerationLLM()
    controller = _build_pipeline(
        llm_output=json.dumps({"intent": "knowledge", "confidence": 0.9}),
        records=records,
        gen_llm=gen_llm,
        retrieve_results=[],
    )

    text = await controller.handle_buyer_turn(
        shop_id="s1", body="有货吗", product_ref_ids=[]
    )

    assert text == "转人工"
    assert len(records) == 1
    assert gen_llm.calls == []
