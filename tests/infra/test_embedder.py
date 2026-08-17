"""infra Embedder 测试（TDD 红阶段）。"""

import os

import allure
import pytest
from pydantic import ValidationError


def test_embedding_dimension_is_required_when_missing() -> None:
    """缺少 EMBEDDING_DIMENSION 时 Settings 构造会因字段必填而失败。"""
    from app.infra.config import Settings

    old = os.environ.pop("EMBEDDING_DIMENSION", None)
    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]
    finally:
        if old is not None:
            os.environ["EMBEDDING_DIMENSION"] = old


@pytest.mark.integration
@allure.epic("infra")
@allure.feature("embedder")
@allure.title("MockEmbedder 返回配置维度向量")
def test_mock_embedder_returns_configured_dimension() -> None:
    """EMBEDDING_PROVIDER=mock 时 embed_texts 返回与 embedding_dimension 等长向量。"""
    from app.infra.config import get_settings
    from app.infra.embedder import get_embedder

    settings = get_settings()
    embedder = get_embedder()
    assert embedder.dimension == settings.embedding_dimension

    vectors = embedder.embed_texts(["测试"])
    assert len(vectors) == 1
    assert len(vectors[0]) == settings.embedding_dimension


@pytest.mark.integration
@allure.epic("infra")
@allure.feature("embedder")
@allure.title("配置维度与 Embedder 不一致时 fail-fast")
def test_embedder_dimension_mismatch_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_embedder().dimension 与 settings.embedding_dimension 不一致时初始化失败。"""
    from app.infra import embedder as embedder_module
    from app.infra.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings, "embedding_dimension", settings.embedding_dimension + 1
    )

    embedder_module._embedder_instance = None  # noqa: SLF001 — 测试重置单例

    with pytest.raises(RuntimeError, match="dimension"):
        embedder_module.get_embedder()
