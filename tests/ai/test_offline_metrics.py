"""离线指标清单红门禁测试（TDD 红阶段）。

覆盖 spec ai-ragas-eval「Offline RAGAS scores Faithfulness and Context recall only」：
- 启用指标 SHALL 含 Faithfulness 与 Context recall（或 RAGAS 类名等价）；
- SHALL NOT 含 Context precision / Answer(Response) Relevancy。

CI 安全由 import 型断言隐式保证：在无 eval 依赖（无 ragas）的环境 import
``app.ai.evals.metrics`` 本身即验证该模块不依赖 ragas。

红门禁：``app.ai.evals.metrics`` 尚未实现（§3/§5 落地前）→ 应红。
"""

import allure


def _normalize(name: str) -> str:
    """规范化指标名：去下划线/空格、小写，便于等价类名匹配。"""
    return name.replace("_", "").replace(" ", "").lower()


def _enabled_metrics() -> set[str]:
    from app.ai.evals.metrics import enabled_metrics

    metrics = enabled_metrics()
    assert metrics, "enabled_metrics() 不应返回空集"
    return {_normalize(m) for m in metrics}


@allure.epic("ai")
@allure.feature("offline_metrics")
@allure.title("启用指标包含 faithfulness 与 context_recall。")
def test_enabled_metrics_include_faithfulness_and_context_recall() -> None:
    """离线打分 SHALL 包含 Faithfulness 与 Context recall（或 RAGAS 类名等价）。"""
    normalized = _enabled_metrics()
    assert any("faithfulness" in n for n in normalized)
    assert any("contextrecall" in n for n in normalized)


@allure.epic("ai")
@allure.feature("offline_metrics")
@allure.title("启用指标不包含 context_precision / answer_relevancy。")
def test_enabled_metrics_exclude_precision_and_relevancy() -> None:
    """本 change SHALL NOT 启用 Context precision / Answer(Response) Relevancy。"""
    normalized = _enabled_metrics()
    assert not any("contextprecision" in n for n in normalized)
    assert not any(
        "answerrelevancy" in n or "responserelevancy" in n for n in normalized
    )
