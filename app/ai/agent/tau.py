"""τ 最小门禁纯函数。

语义：分数 **大于等于** 阈值即通过（进入知识检索 / 生成）；低于阈值 → 拒答转人工。
本刀唯一分数源是 NLU 置信度；空检索在 handler 层视为未达 τ（design D6）。
"""


def passed_tau(score: float, threshold: float) -> bool:
    """``score >= threshold`` 即通过 τ 门禁。"""
    return score >= threshold
