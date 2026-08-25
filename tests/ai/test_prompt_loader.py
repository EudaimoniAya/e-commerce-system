"""提示词 Git 登记加载器测试（TDD 红阶段）。

覆盖 spec ai-support-agent「Prompts are git-registered」：
按 id 读取 YAML（含 id/version/template）；缺登记文件抛出明确错误，不静默用空串。
"""

from pathlib import Path

import allure
import pytest

from app.ai.prompts.loader import PromptLoader, PromptNotFoundError


@allure.epic("ai")
@allure.feature("prompt_loader")
@allure.title("按 id 加载提示词返回登记 id、非空 version 与 template。")
def test_prompt_loader_loads_by_id(tmp_path: Path) -> None:
    """loader 从 ``{base_dir}/{prompt_id}.yaml`` 读出 id/version/text。"""
    (tmp_path / "nlu_route.yaml").write_text(
        "id: nlu_route\nversion: v1\ntemplate: 路由提示 {body}\n",
        encoding="utf-8",
    )

    loader = PromptLoader(base_dir=tmp_path)
    prompt = loader.load("nlu_route")

    assert prompt.id == "nlu_route"
    assert prompt.version == "v1"
    assert prompt.text == "路由提示 {body}"


@allure.epic("ai")
@allure.feature("prompt_loader")
@allure.title("加载不存在的提示词 id 抛出明确错误。")
def test_prompt_loader_missing_id_raises(tmp_path: Path) -> None:
    """缺登记文件时抛出可捕获的明确错误，不得返回空串。"""
    loader = PromptLoader(base_dir=tmp_path)

    with pytest.raises(PromptNotFoundError):
        loader.load("missing")
