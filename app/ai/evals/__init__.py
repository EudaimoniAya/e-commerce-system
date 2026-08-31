"""离线 RAG 评测（ai-ragas-eval）：黄金样本 → 叶子 adapter → RAGAS 打分。

叶子 adapter 只消费 ``retrieve_chunks`` + 登记提示词 + ``LLMClient``，
不走 ``IntentController`` / ``/ai/shops/{shop_id}/replies``（design 决策 1/3）。
本包可在缺 eval 依赖（ragas 未装）时独立导入；真打分仅在 ``uv sync --group eval`` 后离线运行。
"""
