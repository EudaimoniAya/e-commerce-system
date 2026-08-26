# infra-ai-pgvector

## MODIFIED Requirements

### Requirement: Embedder abstraction and dimension validation

系统 SHALL 在 `app/infra/embedder.py` 提供 `Embedder` 协议（含 `dimension` 属性与 `embed_texts` 方法）、`get_embedder()` 工厂及 **`FakeEmbedder`**（CI 与默认测试使用的产品侧假实现）。系统 SHALL 在应用启动时校验 **`get_embedder().dimension == settings.embedding_dimension`**，不一致时 **SHALL** fail-fast。向量写入前 SHALL 校验向量长度等于 `dimension`。SHALL NOT 保留名为 `MockEmbedder` 的产品类。`EMBEDDING_PROVIDER=mock` 取值 SHALL NOT 改名。

#### Scenario: FakeEmbedder 返回配置维度

- **WHEN** `EMBEDDING_PROVIDER=mock` 且 `EMBEDDING_DIMENSION=1024`
- **THEN** `get_embedder().embed_texts(["测试"])` SHALL 返回长度为 1 的列表，且每个向量长度为 1024

#### Scenario: 配置维度与 Embedder 不一致时启动失败

- **WHEN** `EMBEDDING_DIMENSION` 与 `get_embedder().dimension` 不一致
- **THEN** 应用启动或 embedder 初始化 SHALL 失败并给出明确错误信息

#### Scenario: CI 使用 mock provider

- **WHEN** CI workflow 设置 `EMBEDDING_PROVIDER=mock`
- **THEN** integration 测试 SHALL NOT 调用外部 Embedding HTTP API
