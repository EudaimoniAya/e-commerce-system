"""AST 应用层纪律合成用例（ai ∈ DOMAINS + R5）。

覆盖 spec ai-domain-composition：
- 业务域 import app.ai.* 一律违规
- app/ai/** 除 deps.py 外 import 别域 deps 违规
- app/ai/deps.py 取 get_media_service 放行
"""

import ast
import importlib.util
import types
from pathlib import Path

import allure

_SCRIPT = Path("scripts/check_app_layer_discipline.py")


def _load_discipline() -> types.ModuleType:
    """加载 AST 门禁脚本（非包模块，按路径 exec）。"""
    spec = importlib.util.spec_from_file_location("check_app_layer_discipline", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _findings(rel: str, source: str) -> list[object]:
    """对合成源码跑 import 检查，返回 findings。"""
    module = _load_discipline()
    domain = rel.split("/")[0]
    checker = module.AppLayerDisciplineChecker(rel, domain, ast.parse(source), {})
    checker.check_imports()
    return list(checker.findings)


@allure.epic("ops")
@allure.feature("app_layer_discipline")
@allure.title("DOMAINS 含 ai")
def test_domains_includes_ai() -> None:
    """ai 纳入跨域门禁，否则业务→AI / R5 都套空。"""
    module = _load_discipline()
    assert "ai" in module.DOMAINS


@allure.epic("ops")
@allure.feature("app_layer_discipline")
@allure.title("业务域 import app.ai 一律违规")
def test_business_domain_import_ai_is_violation() -> None:
    """catalog 即使 import AI service 也不得走 service 白名单放行。"""
    findings = _findings(
        "catalog/service.py",
        "from app.ai.rag.retrieval.service import retrieve_chunks\n",
    )
    assert findings


@allure.epic("ops")
@allure.feature("app_layer_discipline")
@allure.title("AI service import 别域 deps 违规")
def test_ai_service_import_foreign_deps_is_violation() -> None:
    """indexing/service 不得 from app.media.deps import get_media_service。"""
    findings = _findings(
        "ai/rag/indexing/service.py",
        "from app.media.deps import get_media_service\n",
    )
    assert findings


@allure.epic("ops")
@allure.feature("app_layer_discipline")
@allure.title("AI deps.py 取 get_media_service 放行")
def test_ai_deps_import_media_service_allowed() -> None:
    """组合根是唯一允许 import 别域 deps 的 AI 模块。"""
    module = _load_discipline()
    assert "ai" in module.DOMAINS
    findings = _findings(
        "ai/deps.py",
        "from app.media.deps import get_media_service\n",
    )
    assert findings == []
