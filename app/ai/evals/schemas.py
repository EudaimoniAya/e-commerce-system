"""评测 DTO：叶子 adapter 产出的 ``SingleTurnSample``。

数据流（design 决策 1）：黄金样本 → ``build_eval_sample`` → ``SingleTurnSample``
→ RAGAS Faithfulness / Context recall。``reference`` / ``reference_context_ids``
来自黄金样本（§4 提交），不属叶子输出；runner 侧再合并。
"""

from pydantic import BaseModel


class SingleTurnSample(BaseModel):
    """一条评测样本的叶子填充结果（RAGAS 单轮 Sample 前身）。

    - ``retrieved_contexts``：与检索结果 ``content_text`` 顺序一致；
    - ``retrieved_context_ids``：``"{document_id}:{chunk_index}"``；
    - ``response``：有 chunk 时为 ``rag_answer`` 生成正文；空检索为 ``suggest_human`` 登记正文。
    """

    id: str
    question: str
    shop_id: str
    product_id: str | None = None
    retrieved_contexts: list[str]
    retrieved_context_ids: list[str]
    response: str
