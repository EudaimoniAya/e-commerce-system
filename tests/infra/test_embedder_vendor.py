"""infra 真厂商 Embedder 单测（httpx mock；TDD 红阶段）。

覆盖 spec infra-ai-pgvector「Vendor embedder HTTP implementations」：
- mock 拦截下 ``zhipu`` / ``dashscope`` 返回 ``EMBEDDING_DIMENSION``（1024）维向量
- 请求发往该厂商 URL

注入方式：经 ``_client`` 字段注入带 ``httpx.MockTransport`` 的 ``httpx.Client``
（绿阶段 5.1 实现该字段与真实 HTTP）。现状 ``embed_texts`` 抛 ``NotImplementedError``
即为红（不编写真 HTTP 实现）。CI 仍 ``EMBEDDING_PROVIDER=mock``。
"""

import allure
import httpx

from app.infra.embedder import DashscopeEmbedder, ZhipuEmbedder

_ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
_DASHSCOPE_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/"
    "embeddings/text-embedding/text-embedding"
)
_DIMENSION = 1024


def _embedding_response(request: httpx.Request, expected_url: str) -> httpx.Response:
    """断言请求发往厂商 URL，并返回合法 embedding 响应（1024 维）。"""
    assert str(request.url).startswith(expected_url)
    return httpx.Response(
        200,
        json={"data": [{"embedding": [0.1] * _DIMENSION, "index": 0}]},
    )


@allure.epic("infra")
@allure.feature("embedder_vendor")
@allure.title("httpx mock 下 zhipu 返回配置维度向量。")
def test_zhipu_embed_texts_returns_configured_dimension() -> None:
    """``EMBEDDING_DIMENSION=1024`` 时 zhipu embed_texts 返回 1 条 1024 维向量。"""
    transport = httpx.MockTransport(
        lambda request: _embedding_response(request, _ZHIPU_URL)
    )
    with httpx.Client(transport=transport) as client:
        embedder = ZhipuEmbedder(
            dimension=_DIMENSION,
            api_key="test-key",
            model="embedding-3",
        )
        embedder._client = client  # noqa: SLF001 — 注入 mock transport（绿阶段实现 _client）
        vectors = embedder.embed_texts(["测试"])

    assert len(vectors) == 1
    assert len(vectors[0]) == _DIMENSION


@allure.epic("infra")
@allure.feature("embedder_vendor")
@allure.title("httpx mock 下 dashscope 返回配置维度向量。")
def test_dashscope_embed_texts_returns_configured_dimension() -> None:
    """``EMBEDDING_DIMENSION=1024`` 时 dashscope embed_texts 返回 1 条 1024 维向量。"""
    transport = httpx.MockTransport(
        lambda request: _embedding_response(request, _DASHSCOPE_URL)
    )
    with httpx.Client(transport=transport) as client:
        embedder = DashscopeEmbedder(
            dimension=_DIMENSION,
            api_key="test-key",
            model="text-embedding-v3",
        )
        embedder._client = client  # noqa: SLF001 — 注入 mock transport（绿阶段实现 _client）
        vectors = embedder.embed_texts(["测试"])

    assert len(vectors) == 1
    assert len(vectors[0]) == _DIMENSION
