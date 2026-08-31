"""离线 RAGAS 指标清单（ai-ragas-eval §1.8 / §5）。

CI 安全：本模块**不** import ragas —— 缺 eval 依赖（无 ``uv sync --group eval``）也能导入。
``enabled_metrics()`` 返回字符串名；runner 侧再按名映射为 RAGAS 指标对象
（惰性 import ragas，见 ``app.ai.evals.runner``）。
"""

from __future__ import annotations

_ENABLED_METRIC_NAMES: tuple[str, ...] = ("faithfulness", "context_recall")


def enabled_metrics() -> list[str]:
    """本刀启用的离线指标名（RAGAS Faithfulness + Context recall）。

    Context precision / Answer(Response) Relevancy SHALL NOT 启用（spec）。
    """
    return list(_ENABLED_METRIC_NAMES)
