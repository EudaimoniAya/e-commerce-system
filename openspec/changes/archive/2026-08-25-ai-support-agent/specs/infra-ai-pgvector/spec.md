# infra-ai-pgvector

## ADDED Requirements

### Requirement: Vendor embedder HTTP implementations

当 `EMBEDDING_PROVIDER` 为 `zhipu` 或 `dashscope` 时，对应 Embedder SHALL 发起真实 Embedding HTTP 并返回长度为 `dimension` 的向量列表。单测 SHALL 用 httpx mock 断言请求发往该厂商 URL，且返回向量维度等于 `EMBEDDING_DIMENSION`。CI 与默认 pytest SHALL 继续 `EMBEDDING_PROVIDER=mock`，SHALL NOT 调用外部 Embedding HTTP。HTTP 失败或返回维度不符 SHALL fail-fast（抛错），SHALL NOT 静默填 Mock 向量。

#### Scenario: mock 拦截下 zhipu 返回配置维度

- **WHEN** `EMBEDDING_PROVIDER=zhipu` 且 HTTP 被 mock 为合法 embedding 响应、`EMBEDDING_DIMENSION=1024`
- **THEN** `embed_texts(["测试"])` SHALL 返回 1 条长度为 1024 的向量

#### Scenario: mock 拦截下 dashscope 返回配置维度

- **WHEN** `EMBEDDING_PROVIDER=dashscope` 且 HTTP 被 mock 为合法 embedding 响应、`EMBEDDING_DIMENSION=1024`
- **THEN** `embed_texts(["测试"])` SHALL 返回 1 条长度为 1024 的向量

#### Scenario: CI 仍不打外部 embedding

- **WHEN** CI workflow 设置 `EMBEDDING_PROVIDER=mock`
- **THEN** integration 测试 SHALL NOT 调用外部 Embedding HTTP API
