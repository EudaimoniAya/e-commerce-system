"""τ 最小门禁纯函数边界测试（TDD 红阶段）。

覆盖 spec ai-support-agent「Tau gate is a single threshold」：
分数 ≥ 阈值 → 通过；低于阈值 → 未通过。
"""

import allure
from app.ai.agent.tau import passed_tau


@allure.epic("ai")
@allure.feature("agent_tau")
@allure.title("分数低于阈值未通过 τ。")
def test_passed_tau_below_threshold_is_false() -> None:
    """score < threshold → 未通过（走转人工兜底）。"""
    assert passed_tau(0.1, 0.3) is False


@allure.epic("ai")
@allure.feature("agent_tau")
@allure.title("分数等于阈值通过 τ。")
def test_passed_tau_at_threshold_is_true() -> None:
    """score == threshold → 通过（边界含等号）。"""
    assert passed_tau(0.3, 0.3) is True


@allure.epic("ai")
@allure.feature("agent_tau")
@allure.title("分数高于阈值通过 τ。")
def test_passed_tau_above_threshold_is_true() -> None:
    """score > threshold → 通过。"""
    assert passed_tau(0.9, 0.3) is True


@allure.epic("ai")
@allure.feature("agent_tau")
@allure.title("阈值 0 时任意非负分数通过。")
def test_passed_tau_zero_threshold() -> None:
    """threshold=0 时 0 与 1 均通过。"""
    assert passed_tau(0.0, 0.0) is True
    assert passed_tau(1.0, 0.0) is True
