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


def _build_embedder() -> Embedder:
    """按配置 provider 构建 Embedder（当前仅 MockEmbedder）。"""
    settings = get_settings()
    if settings.embedding_provider == "mock":
        return MockEmbedder(settings.embedding_dimension)
    # zhipu / dashscope 厂商骨架在 Task 4.2 补齐
    raise ValueError(f"不支持的 embedding_provider: {settings.embedding_provider}")


def get_embedder() -> Embedder:
    """懒加载 Embedder 单例，并在每次调用时校验维度与 schema 配置一致（fail-fast）。"""
    global _embedder_instance, _schema_dimension
    settings = get_settings()
    if _embedder_instance is None:
        _embedder_instance = _build_embedder()
        if _schema_dimension is None:
            _schema_dimension = settings.embedding_dimension
    if _embedder_instance.dimension != _schema_dimension:
        raise RuntimeError(
            "embedding dimension mismatch: "
            f"provider={_embedder_instance.dimension}, configured={_schema_dimension}"
        )
    return _embedder_instance
