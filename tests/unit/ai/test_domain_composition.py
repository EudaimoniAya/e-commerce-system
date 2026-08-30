"""ai-domain-composition 与 support-conversations 符号契约测试（TDD 红阶段）。

覆盖：
- support-conversations「无 Port 与工厂符号」：无 ``BuyerTurnAiHandler`` /
  ``register_buyer_turn_handler_factory``
- ai-domain-composition「组合根装配客服编排器」：``build_intent_controller`` 可调用、
  ``build_buyer_turn_handler`` 不存在
- ai-support-agent「Prompts are git-registered」：``ask_about_product`` 可加载

红阶段：Port / 旧工厂符号仍存在、``build_intent_controller`` 未改名、
``ask_about_product.yaml`` 未登记 → 断言全部失败（红）。
**不编写** 改名与提示词文件（§2.1 改名登记、§3 拆 Port 后转绿）。
"""

import importlib


def test_no_buyer_turn_ai_handler_symbol() -> None:
    """``app/support/`` SHALL NOT 保留 ``BuyerTurnAiHandler``（模块随 §3 删除亦视为通过）。"""
    try:
        module = importlib.import_module("app.support.ports")
    except ModuleNotFoundError:
        return  # §3 删除 ports.py → 模块不存在，符号必然缺失
    assert not hasattr(module, "BuyerTurnAiHandler")


def test_no_register_buyer_turn_handler_factory() -> None:
    """``app/support/deps.py`` SHALL NOT 保留 ``register_buyer_turn_handler_factory``。"""
    import app.support.deps as deps

    assert not hasattr(deps, "register_buyer_turn_handler_factory")


def test_build_intent_controller_is_callable() -> None:
    """``app/ai/deps.py`` SHALL 提供可调用 ``build_intent_controller``。"""
    from app.ai.deps import build_intent_controller

    assert callable(build_intent_controller)


def test_build_buyer_turn_handler_absent() -> None:
    """``build_buyer_turn_handler`` SHALL 改名删除（不再存在）。"""
    import app.ai.deps as deps

    assert not hasattr(deps, "build_buyer_turn_handler")


def test_ask_about_product_prompt_loadable() -> None:
    """``ask_about_product`` SHALL 可经加载器按 id 读取，含非空 version/template。"""
    from app.ai.deps import build_prompt_loader

    prompt = build_prompt_loader().load("ask_about_product")

    assert prompt.id == "ask_about_product"
    assert prompt.version
    assert prompt.text
