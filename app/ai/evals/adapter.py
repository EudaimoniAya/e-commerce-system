"""评测叶子 adapter：黄金样本 → ``SingleTurnSample``（retrieve + rag_answer 生成）。

契约（design 决策 1/3，spec ai-ragas-eval「Leaf eval adapter fills RAGAS
single-turn fields」）：
- 对样本调 ``retrieve(shop_id, query=question, product_id=…)``（product_id null → 不传过滤）；
- ``retrieved_contexts`` = 各 chunk ``content_text`` 顺序一致；
- ``retrieved_context_ids`` = ``"{document_id}:{chunk_index}"``；
- 有 chunk：加载登记提示词 ``rag_answer`` 填 ``{chunks}`` / ``{body}``，调 ``LLMClient.generate``；
- 空检索：SHALL NOT 调生成，``response`` = ``suggest_human`` 登记正文；
- 叶子 SHALL NOT 实例化 ``IntentController`` / 打 ``/ai/shops/{shop_id}/replies``：
  只收注入的 ``retrieve`` / ``generation_llm`` / ``prompt_loader``，无 HTTP 入口。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.ai.evals.schemas import SingleTurnSample
from app.ai.llm.client import LLMClient
from app.ai.prompts.loader import PromptLoader
from app.ai.rag.schemas import RetrievedChunk

_RAG_ANSWER_PROMPT_ID = "rag_answer"
_SUGGEST_HUMAN_PROMPT_ID = "suggest_human"


async def build_eval_sample(
    sample: dict,
    *,
    retrieve: Callable[..., Awaitable[list[RetrievedChunk]]],
    generation_llm: LLMClient,
    prompt_loader: PromptLoader,
) -> SingleTurnSample:
    """把一条黄金样本喂给叶子管线，产出去打分的 ``SingleTurnSample``。

    ``retrieve`` 注入（与 ``retrieve_chunks`` 同签名）；``product_id`` 为 null /
    缺省时整店检索（不传商品过滤）。空检索不调生成 LLM，回落 ``suggest_human``
    登记正文（与 ``KnowledgeHandler`` 空检索一致，design 决策 3）。
    """
    shop_id = sample["shop_id"]
    question = sample["question"]
    product_id = sample.get("product_id")

    chunks = await retrieve(shop_id=shop_id, query=question, product_id=product_id)

    retrieved_contexts = [chunk.content_text for chunk in chunks]
    retrieved_context_ids = [
        f"{chunk.document_id}:{chunk.chunk_index}" for chunk in chunks
    ]

    if not chunks:
        fallback = prompt_loader.load(_SUGGEST_HUMAN_PROMPT_ID)
        response = fallback.text
    else:
        prompt = prompt_loader.load(_RAG_ANSWER_PROMPT_ID)
        chunk_text = "\n".join(chunk.content_text for chunk in chunks)
        content = prompt.text.replace("{chunks}", chunk_text).replace(
            "{body}", question
        )
        response = await generation_llm.generate([{"role": "user", "content": content}])

    return SingleTurnSample(
        id=sample["id"],
        question=question,
        shop_id=shop_id,
        product_id=product_id,
        retrieved_contexts=retrieved_contexts,
        retrieved_context_ids=retrieved_context_ids,
        response=response,
    )
