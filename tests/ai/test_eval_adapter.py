"""评测叶子 adapter 红门禁测试（TDD 红阶段）。

覆盖 spec ai-ragas-eval「Leaf eval adapter fills RAGAS single-turn fields」。
模块路径由红测锁定：``app.ai.evals.adapter.build_eval_sample``（§3.1 落地）。

契约（design 决策 1/3）：
- 对样本调 ``retrieve(shop_id, query=question, product_id=…)``（product_id null → 不传过滤）；
- ``retrieved_contexts`` = 各 chunk ``content_text`` 顺序一致；
- ``retrieved_context_ids`` = ``"{document_id}:{chunk_index}"``；
- 有 chunk：加载登记提示词 ``rag_answer`` 填 ``{chunks}`` / ``{body}``，调 ``LLMClient.generate``；
- 空检索：SHALL NOT 调 ``generate``，``response`` = ``suggest_human`` 登记正文；
- 叶子 SHALL NOT 实例化 ``IntentController`` / 打 ``/ai/shops/{shop_id}/replies``：
  adapter 只收注入的 ``retrieve`` / ``generation_llm`` / ``prompt_loader``，无 HTTP 入口
  （本文件行为测全程无 AsyncClient），结构性保证不走客服 HTTP / 编排器。

红门禁：adapter 尚未实现 → 行为测 ImportError → 应红。
"""

from collections.abc import Awaitable, Callable

import allure

from app.ai.llm.client import FakeLLMClient
from app.ai.prompts.loader import LoadedPrompt
from app.ai.rag.schemas import RetrievedChunk

_SHOP_ID = "shop-1"
_QUESTION = "这个产品有哪些规格？"

# 与 app/ai/prompts/*.yaml 结构一致的最小模板（登记正文）
_TEMPLATES = {
    "rag_answer": "你是客服。检索资料：\n{chunks}\n\n买家提问：{body}",
    "suggest_human": "转人工文案",
}


def _chunk(document_id: str, chunk_index: int, content_text: str) -> RetrievedChunk:
    """数据载体：直接构造 RetrievedChunk，非测试替身。"""
    return RetrievedChunk(
        shop_id=_SHOP_ID,
        product_id="p-1",
        document_id=document_id,
        chunk_index=chunk_index,
        content_text=content_text,
        score=0.5,
    )


def _sample(*, product_id: str | None = None) -> dict:
    """一条黄金样本（dict 形状 = samples.jsonl 单行）。"""
    return {
        "id": "s1",
        "question": _QUESTION,
        "shop_id": _SHOP_ID,
        "product_id": product_id,
    }


def _spy_retrieve(
    records: list[dict], chunks: list[RetrievedChunk]
) -> Callable[..., Awaitable[list[RetrievedChunk]]]:
    """记录调用参数、返回注入 chunks 的 spy retrieve（对齐 retrieve_chunks 签名）。"""

    async def _retrieve(
        shop_id: str,
        query: str,
        top_k: int = 5,
        product_id: str | None = None,
    ) -> list[RetrievedChunk]:
        records.append(
            {
                "shop_id": shop_id,
                "query": query,
                "top_k": top_k,
                "product_id": product_id,
            }
        )
        return chunks

    return _retrieve


class _RecordingPromptLoader:
    """dict 驱动 loader：记录 ``load(id)`` 调用（断言 rag_answer / suggest_human 登记被读）。"""

    def __init__(self, templates: dict[str, str]) -> None:
        self._templates = templates
        self.loaded: list[str] = []

    def load(self, prompt_id: str) -> LoadedPrompt:
        self.loaded.append(prompt_id)
        if prompt_id not in self._templates:
            raise KeyError(prompt_id)
        return LoadedPrompt(text=self._templates[prompt_id], id=prompt_id, version="v1")


async def _build_eval_sample(
    sample: dict,
    *,
    retrieve: Callable[..., Awaitable[list[RetrievedChunk]]],
    generation_llm: FakeLLMClient,
    prompt_loader: _RecordingPromptLoader,
) -> object:
    """延迟导入 adapter（红阶段模块不存在 → ImportError）。"""
    from app.ai.evals.adapter import build_eval_sample

    return await build_eval_sample(
        sample,
        retrieve=retrieve,
        generation_llm=generation_llm,
        prompt_loader=prompt_loader,
    )


@allure.epic("ai")
@allure.feature("eval_adapter")
@allure.title(
    "retrieved_contexts 与 content_text 顺序一致，retrieved_context_ids 为 document_id:chunk_index。"
)
async def test_fills_retrieved_contexts_and_ids_in_chunk_order() -> None:
    """注入 Fake 检索返回带 document_id/chunk_index/content_text 的 chunk 列表。"""
    records: list[dict] = []
    chunks = [
        _chunk("doc-a", 0, "规格A"),
        _chunk("doc-b", 2, "规格B"),
    ]
    result = await _build_eval_sample(
        _sample(),
        retrieve=_spy_retrieve(records, chunks),
        generation_llm=FakeLLMClient("答复"),
        prompt_loader=_RecordingPromptLoader(_TEMPLATES),
    )

    assert result.retrieved_contexts == ["规格A", "规格B"]
    assert result.retrieved_context_ids == ["doc-a:0", "doc-b:2"]


@allure.epic("ai")
@allure.feature("eval_adapter")
@allure.title("product_id 为 None 时调用检索不传商品过滤。")
async def test_product_id_none_passes_no_filter_to_retrieve() -> None:
    """整店检索：product_id 缺省/null 时不传商品过滤（spy 记录为 None）。"""
    records: list[dict] = []
    await _build_eval_sample(
        _sample(product_id=None),
        retrieve=_spy_retrieve(records, [_chunk("doc-a", 0, "规格A")]),
        generation_llm=FakeLLMClient("答复"),
        prompt_loader=_RecordingPromptLoader(_TEMPLATES),
    )

    assert records[-1]["shop_id"] == _SHOP_ID
    assert records[-1]["query"] == _QUESTION
    assert records[-1]["product_id"] is None


@allure.epic("ai")
@allure.feature("eval_adapter")
@allure.title(
    "有 chunk 时加载 rag_answer 并调 LLMClient.generate（chunks/问句按模板填写）。"
)
async def test_with_chunks_loads_rag_answer_and_calls_generate() -> None:
    """有 chunk：mock loader 断言 load(\"rag_answer\") 被调，模板填 chunks 与问句。"""
    records: list[dict] = []
    llm = FakeLLMClient("根据资料回答")
    loader = _RecordingPromptLoader(_TEMPLATES)
    result = await _build_eval_sample(
        _sample(),
        retrieve=_spy_retrieve(records, [_chunk("doc-a", 0, "规格A")]),
        generation_llm=llm,
        prompt_loader=loader,
    )

    assert loader.loaded == ["rag_answer"]
    assert len(llm.calls) == 1
    content = llm.calls[0][0]["content"]
    assert "{chunks}" not in content and "{body}" not in content
    assert "规格A" in content and _QUESTION in content
    assert "检索资料：" in content and "买家提问：" in content
    assert result.response == "根据资料回答"


@allure.epic("ai")
@allure.feature("eval_adapter")
@allure.title("空检索不调生成，response 等于 suggest_human 登记正文。")
async def test_empty_retrieval_no_generate_uses_suggest_human() -> None:
    """空检索：SHALL NOT 调 LLMClient.generate，response = suggest_human 正文。"""
    records: list[dict] = []
    llm = FakeLLMClient("不应被调用")
    loader = _RecordingPromptLoader(_TEMPLATES)
    result = await _build_eval_sample(
        _sample(),
        retrieve=_spy_retrieve(records, []),
        generation_llm=llm,
        prompt_loader=loader,
    )

    assert llm.calls == []
    assert loader.loaded == ["suggest_human"]
    assert result.response == _TEMPLATES["suggest_human"]
