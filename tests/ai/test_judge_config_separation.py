"""裁判与生成配置分离红门禁测试（TDD 红阶段）。

覆盖 spec ai-ragas-eval「Offline RAGAS scores…CI 不跑裁判」：
- Settings SHALL 可读独立变量 ``RAGAS_JUDGE_API_KEY`` / ``RAGAS_JUDGE_BASE_URL`` /
  ``RAGAS_JUDGE_MODEL``（与生成 ``LLM_*`` 不同名）；
- 缺省（env 未设）时 Settings 构造不抛错、评测相关 pytest 仍绿。

红门禁：裁判配置项尚未写入 Settings（§2.1 落地前）→ 字段断言应红。
"""

import allure

from app.infra.config import Settings

_JUDGE_FIELDS = {
    "ragas_judge_api_key",
    "ragas_judge_base_url",
    "ragas_judge_model",
}


def _model_fields() -> set[str]:
    return set(Settings.model_fields)


@allure.epic("ai")
@allure.feature("judge_config_separation")
@allure.title("Settings 暴露 RAGAS_JUDGE_* 三个独立字段。")
def test_settings_expose_judge_fields() -> None:
    """裁判配置项可读（§2.1 落地前缺字段 → 本测红）。"""
    fields = _model_fields()
    missing = _JUDGE_FIELDS - fields
    assert not missing, f"Settings 缺少裁判字段（§2.1 落地前本测应红）: {sorted(missing)}"


@allure.epic("ai")
@allure.feature("judge_config_separation")
@allure.title("裁判字段与生成 LLM_* 不同名。")
def test_judge_fields_distinct_from_generation_llm() -> None:
    """裁判与生成 SHALL 分离：RAGAS_JUDGE_* 与 LLM_* 字段名互斥。"""
    fields = _model_fields()
    llm_fields = {f for f in fields if f.startswith("llm_")}
    assert _JUDGE_FIELDS.isdisjoint(llm_fields), (
        f"裁判字段不得与生成 LLM 字段同名: {sorted(_JUDGE_FIELDS & llm_fields)}"
    )


@allure.epic("ai")
@allure.feature("judge_config_separation")
@allure.title("未设 RAGAS_JUDGE_* 时 Settings 构造不抛错，缺省为 None。")
def test_settings_constructs_without_judge_env() -> None:
    """缺省（env 未设）时构造不抛错、裁判项为 None（CI 不要求裁判密钥）。"""
    settings = Settings()
    assert settings.ragas_judge_api_key is None
    assert settings.ragas_judge_base_url is None
    assert settings.ragas_judge_model is None
