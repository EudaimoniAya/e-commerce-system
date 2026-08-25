"""注册意图的处理器：本 change 仅知识类（``retrieve_chunks`` + ``rag_answer`` + 生成 LLM）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger

from app.ai.llm.client import LLMClient
from app.ai.prompts.loader import PromptLoader

# 本 handler 消费的生成提示词登记 id（日志带 prompt_id/version 用）
_RAG_ANSWER_PROMPT_ID = "rag_answer"


def _product_id_from_refs(product_ref_ids: list[str]) -> str | None:
    """按本条消息已校验 refs（去重、顺序保留）计算检索过滤键。

    0 个 → ``None``（整店）；1 个 → 该 id；≥2 个 → 取最后一项。
    """
    if not product_ref_ids:
        return None
    return product_ref_ids[-1]


class KnowledgeHandler:
    """知识类意图 handler：先检索，空结果拒答不生成；否则按 ``rag_answer`` 生成。"""

    def __init__(
        self,
        *,
        retrieve: Callable[..., Awaitable[list]],
        generation_llm: LLMClient,
        prompt_loader: PromptLoader,
        fallback_text: str,
    ) -> None:
        self._retrieve = retrieve
        self._generation_llm = generation_llm
        self._prompt_loader = prompt_loader
        self._fallback_text = fallback_text

    async def handle(
        self,
        *,
        shop_id: str,
        body: str,
        product_ref_ids: list[str],
    ) -> str:
        """检索并按 refs 过滤；空检索视为未达 τ（拒答/转人工文案，不调生成 LLM）。"""
        product_id = _product_id_from_refs(product_ref_ids)
        chunks = await self._retrieve(
            shop_id=shop_id,
            query=body,
            product_id=product_id,
        )
        if not chunks:
            return self._fallback_text

        prompt = self._prompt_loader.load(_RAG_ANSWER_PROMPT_ID)
        chunk_text = "\n".join(chunk.content_text for chunk in chunks)
        content = prompt.text.replace("{chunks}", chunk_text).replace("{body}", body)
        # version 来自登记加载器（LoadedPrompt）；测试注入的 fake 可省略
        logger.info(
            "知识类生成",
            prompt_id=_RAG_ANSWER_PROMPT_ID,
            version=getattr(prompt, "version", ""),
            shop_id=shop_id,
        )
        return await self._generation_llm.generate(
            [{"role": "user", "content": content}]
        )
