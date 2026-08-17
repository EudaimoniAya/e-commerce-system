"""Embedding 抽象：Embedder 协议、MockEmbedder、get_embedder() 工厂与维度校验。"""

from __future__ import annotations

import hashlib
from typing import Protocol

from app.infra.config import get_settings

# 进程内唯一 Embedder 单例；测试通过置 None 强制重建。
_embedder_instance: Embedder | None = None
# 首个 Embedder 构建时锁定的 schema/配置维度；重建 instance 不刷新，
# 保证「DB 迁移维度」与「provider 维度」不一致时 fail-fast。
_schema_dimension: int | None = None


class Embedder(Protocol):
    """Embedding 提供者协议：输出固定维度向量。"""

    dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """将文本批量编码为 ``dimension`` 维向量列表。"""


class MockEmbedder:
    """确定性伪向量 Embedder（CI 与默认测试使用）。

    ``embed_texts`` 对每个文本做 SHA-256 确定性散列并循环填满维度：
    同一文本恒得同一向量，便于 pgvector 相似度 smoke 可复现。
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            block = [b / 255.0 for b in digest]
            vectors.append(
                (block * (self.dimension // len(block) + 1))[: self.dimension]
            )
        return vectors


class ZhipuEmbedder:
    """智谱（bigmodel.cn）Embedding API 骨架。

    本 change 仅提供接口骨架（维度 + 参数装配），真实 HTTP 调用留给后续
    需要 ``EMBEDDING_API_KEY`` 的 change / 手动验证。CI 固定 ``mock`` provider，
    不会构造本类，也绝不触发外部 API。
    """

    _API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    def __init__(self, dimension: int, api_key: str, model: str) -> None:
        self.dimension = dimension
        self._api_key = api_key
        self._model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "ZhipuEmbedder 为厂商 API 骨架：本 change 不实现真实调用，"
            "CI 使用 EMBEDDING_PROVIDER=mock"
        )


class DashscopeEmbedder:
    """阿里云百炼（dashscope）Embedding API 骨架。

    与 ``ZhipuEmbedder`` 相同：仅提供接口骨架，真实 HTTP 调用留给后续
    change；CI 固定 ``mock`` provider，不会构造本类。
    """

    _API_BASE_URL = (
        "https://dashscope.aliyuncs.com/api/v1/services/"
        "embeddings/text-embedding/text-embedding"
    )

    def __init__(self, dimension: int, api_key: str, model: str) -> None:
        self.dimension = dimension
        self._api_key = api_key
        self._model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "DashscopeEmbedder 为厂商 API 骨架：本 change 不实现真实调用，"
            "CI 使用 EMBEDDING_PROVIDER=mock"
        )


def _build_embedder(dimension: int) -> Embedder:
    """按配置 provider 构建 Embedder（``dimension`` 为 schema/配置维度）。

    ``mock`` 为 CI 与默认测试 provider；``zhipu`` / ``dashscope`` 为厂商骨架
    （本 change 不实现真实 HTTP 调用，单测通过 mock 该类）。
    """
    settings = get_settings()
    if settings.embedding_provider == "mock":
        return MockEmbedder(dimension)
    if settings.embedding_provider == "zhipu":
        return ZhipuEmbedder(
            dimension=dimension,
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
        )
    if settings.embedding_provider == "dashscope":
        return DashscopeEmbedder(
            dimension=dimension,
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
        )
    raise ValueError(f"不支持的 embedding_provider: {settings.embedding_provider}")


def get_embedder() -> Embedder:
    """懒加载 Embedder 单例，并在每次调用时校验维度与当前配置一致（fail-fast）。

    ``_schema_dimension`` 于首个调用时锁定（对应 DB migration 的 vector 维度）；
    Embedder 始终按该维度构建，避免重建时把配置漂移的错误维度永久留在单例里。
    校验针对 ``settings.embedding_dimension``——运行时配置与 schema 不一致即 fail-fast。
    """
    global _embedder_instance, _schema_dimension
    settings = get_settings()
    if _schema_dimension is None:
        _schema_dimension = settings.embedding_dimension
    if _embedder_instance is None:
        _embedder_instance = _build_embedder(_schema_dimension)
    if _embedder_instance.dimension != settings.embedding_dimension:
        raise RuntimeError(
            "embedding dimension mismatch: "
            f"provider={_embedder_instance.dimension}, "
            f"configured={settings.embedding_dimension}"
        )
    return _embedder_instance
