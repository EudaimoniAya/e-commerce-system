"""生产环境 mock provider 门禁测试（不调 create_app）。

覆盖 spec fake-providers「Production rejects mock llm and embedding providers」：
- APP_ENV=production 且 LLM_PROVIDER=mock → reject_mock_providers_in_production 抛错
  （文案含 production 与 llm）
- APP_ENV=production 且 EMBEDDING_PROVIDER=mock（即使 LLM 非 mock）→ 同样抛错
- APP_ENV=test 且两者均为 mock → 不抛

在测试内直接构造 Settings（monkeypatch 字段方式改写，不碰真实环境），
校验函数单测不启全应用。
"""

import allure
import pytest

from app.infra.config import Settings, reject_mock_providers_in_production


def _settings(**overrides: object) -> Settings:
    """构造完整可用的 Settings，字段可覆盖（默认 test + 双 mock）。"""
    base: dict[str, object] = {
        "database_url": "mysql+asyncmy://u:p@localhost/db",
        "redis_url": "redis://127.0.0.1:6379/1",
        "ai_database_url": "postgresql+asyncpg://u:p@localhost/ai_test",
        "jwt_secret_key": "x" * 32,
        "app_env": "test",
        "llm_provider": "mock",
        "embedding_provider": "mock",
        "embedding_model": "test-model",
        "embedding_dimension": 8,
    }
    base.update(overrides)
    return Settings(**base, _env_file=None)  # type: ignore[arg-type]


@allure.epic("infra")
@allure.feature("config")
@allure.title("production + LLM mock → 启动校验失败。")
def test_production_rejects_mock_llm() -> None:
    """APP_ENV=production 且 LLM_PROVIDER=mock → ValueError，文案含 production 与 llm。"""
    with pytest.raises(ValueError) as exc_info:
        reject_mock_providers_in_production(
            _settings(app_env="production", llm_provider="mock")
        )
    msg = str(exc_info.value).lower()
    assert "production" in msg
    assert "llm" in msg


@allure.epic("infra")
@allure.feature("config")
@allure.title("production + embedding mock（LLM 非 mock）→ 启动校验失败。")
def test_production_rejects_mock_embedding() -> None:
    """APP_ENV=production 且 EMBEDDING_PROVIDER=mock（即使 LLM 非 mock）→ ValueError。"""
    with pytest.raises(ValueError) as exc_info:
        reject_mock_providers_in_production(
            _settings(app_env="production", llm_provider="deepseek")
        )
    msg = str(exc_info.value).lower()
    assert "production" in msg
    assert "embedding" in msg


@allure.epic("infra")
@allure.feature("config")
@allure.title("test 环境允许 mock 组合。")
def test_test_env_allows_mock_providers() -> None:
    """APP_ENV=test 且 llm/embedding 均为 mock → 不抛。"""
    reject_mock_providers_in_production(
        _settings(app_env="test", llm_provider="mock", embedding_provider="mock")
    )
