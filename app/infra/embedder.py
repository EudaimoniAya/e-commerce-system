"""Embedding 抽象：Embedder 协议、MockEmbedder、get_embedder() 工厂与维度校验。"""

from __future__ import annotations

import hashlib
from typing import Protocol

import httpx

from app.infra.config import get_settings

_HTTP_TIMEOUT_SECONDS = 60.0

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
    """智谱（bigmodel.cn）Embedding API（真实 HTTP）。

    测试经 ``_client`` 注入 ``httpx.MockTransport`` 的 ``httpx.Client``（red §1.5 契约）；
    未注入时自建同步 client。HTTP 失败 / 返回维度不符 → fail-fast，不静默填 Mock 向量。
    CI 固定 ``EMBEDDING_PROVIDER=mock``，不会构造本类。
    """

    _API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    def __init__(self, dimension: int, api_key: str, model: str) -> None:
        self.dimension = dimension
        self._api_key = api_key
        self._model = model
        self._client: httpx.Client | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS)
        )
        try:
            response = client.post(
                self._API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            vectors = [item["embedding"] for item in response.json()["data"]]
        finally:
            if self._client is None:
                client.close()
        self._assert_dimension(vectors)
        return vectors

    def _assert_dimension(self, vectors: list[list[float]]) -> None:
        """维度不符 → 抛错（fail-fast），不静默接受。"""
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    "embedding dimension mismatch: "
                    f"got {len(vector)}, expected {self.dimension}"
                )


class DashscopeEmbedder:
    """阿里云百炼（dashscope）Embedding API（真实 HTTP）。

    与 ``ZhipuEmbedder`` 同构：测试经 ``_client`` 注入 mock transport；HTTP 失败 /
    维度不符 fail-fast。CI 固定 ``EMBEDDING_PROVIDER=mock``。
    """

    _API_BASE_URL = (
        "https://dashscope.aliyuncs.com/api/v1/services/"
        "embeddings/text-embedding/text-embedding"
    )

    def __init__(self, dimension: int, api_key: str, model: str) -> None:
        self.dimension = dimension
        self._api_key = api_key
        self._model = model
        self._client: httpx.Client | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(_HTTP_TIMEOUT_SECONDS)
        )
        try:
            response = client.post(
                self._API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            vectors = [item["embedding"] for item in response.json()["data"]]
        finally:
            if self._client is None:
                client.close()
        self._assert_dimension(vectors)
        return vectors

    def _assert_dimension(self, vectors: list[list[float]]) -> None:
        """维度不符 → 抛错（fail-fast），不静默接受。"""
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    "embedding dimension mismatch: "
                    f"got {len(vector)}, expected {self.dimension}"
                )


def _build_embedder(dimension: int) -> Embedder:
    """按配置 provider 构建 Embedder（``dimension`` 为 schema/配置维度）。

    ``mock`` 为 CI 与默认测试 provider；``zhipu`` / ``dashscope`` 为真实 HTTP
    实现（dev 需配置 ``EMBEDDING_API_KEY``；单测经 ``_client`` 注入 mock transport）。
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
