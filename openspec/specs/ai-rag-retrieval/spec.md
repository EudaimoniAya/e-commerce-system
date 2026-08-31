# ai-rag-retrieval

## Purpose

ai 域向量检索与店铺 ACL：对 pgvector 做 shop 隔离 top-K 检索，向 Change 3 智能客服（客服 agent 知识类意图 handler）暴露 `retrieve_chunks` service；本 change 无 public 检索 HTTP，不含 RAGAS 评测。

## Requirements

### Requirement: Shop-scoped vector retrieval ACL

系统 SHALL 在 PG 向量检索 SQL 中 **强制** `WHERE shop_id = :shop_id`；**SHALL NOT** 返回其它店铺的 chunk，即使其向量与 query 更相似。本要求描述的是查询时的店铺过滤，不是 MySQL↔pgvector 防腐层。

#### Scenario: 跨店 query 不泄露

- **WHEN** PG 中存在 shop A 与 shop B 的商品 chunk，且对 shop A 执行 `retrieve_chunks(shop_id=A, query=...)`
- **THEN** 返回列表中每一行的 `shop_id` SHALL 等于 A
- **AND** SHALL NOT 含 shop B 的 `product_id` 或 `content_text`

#### Scenario: SQL 层 shop_id 过滤

- **WHEN** 检查 retrieval repository 生成的向量查询
- **THEN** SHALL 在 WHERE 子句包含与参数绑定的 `shop_id` 条件

### Requirement: Conversation-scoped product filter

当调用方传入 `product_id` 时，系统 SHALL 在向量检索 SQL 中 **同时** 强制 `shop_id` 与 `product_id`；**SHALL NOT** 返回其他商品的 chunk，即使其向量与 query 更相似。未传入 `product_id` 时 SHALL 仅按 `shop_id` 过滤（店铺泛咨询）。查询侧称为按会话范围的过滤，**SHALL NOT** 作为异构库同步防腐层实现。

#### Scenario: 商品对话不串到同店其他商品

- **WHEN** 同店存在商品 A 与商品 B 的 chunk，且执行 `retrieve_chunks(shop_id=店, query=..., product_id=A)`
- **THEN** 返回列表中每一行的 `product_id` SHALL 等于 A
- **AND** SHALL NOT 含商品 B 的 `content_text`

#### Scenario: 未传 product_id 保持整店检索

- **WHEN** 执行 `retrieve_chunks(shop_id=店, query=..., product_id=None)`（或省略该参数）
- **THEN** 结果可含该店多个 `product_id`
- **AND** 每一行的 `shop_id` SHALL 等于该店

#### Scenario: SQL 层同时绑定 shop 与 product

- **WHEN** 检查传入 `product_id` 时 retrieval repository 生成的向量查询
- **THEN** SHALL 在 WHERE 子句包含与参数绑定的 `shop_id` 与 `product_id` 条件

### Requirement: Retrieve chunks service API

系统 SHALL 在 `app.ai.rag.retrieval.service` 提供 `retrieve_chunks(shop_id, query, top_k, product_id=None)` → `list[RetrievedChunk]`，供 **Change 3 客服 agent（ai 域内）** 调用；**SHALL NOT** 经 `app/ai/service.py` 门面转发；**SHALL NOT** 暴露 public HTTP 检索路由；**SHALL NOT** 由 support 或其它业务域直接调用。

#### Scenario: 返回 RetrievedChunk 字段

- **WHEN** 对已 reindex 的 shop 调用 `retrieve_chunks` 且 query 非空、`top_k=5`
- **THEN** 每条结果 SHALL 含 `shop_id`、`product_id`、`document_id`、`chunk_index`、`content_text`、`score`（float，**余弦距离**，`<=>` 语义：**越小越相关**，结果按 score 升序返回）
- **AND** 结果数量 SHALL 小于等于 `top_k`

#### Scenario: 空库返回空列表

- **WHEN** 某 shop 在 PG 无任何 chunk
- **THEN** `retrieve_chunks` SHALL 返回 `[]` 而非抛错

#### Scenario: 空 query 返回空列表

- **WHEN** `query` 为空串或纯空白
- **THEN** `retrieve_chunks` SHALL 返回 `[]` 而非对空文本做 embedding 检索

#### Scenario: top_k 钳制上限

- **WHEN** 调用方传入 `top_k` 超过上限（默认 5，上限 20）
- **THEN** service SHALL 将 `top_k` 钳制到上限（不抛错），SQL 以钳制后值 LIMIT

### Requirement: Brute-force top-K without ANN index

MVP 检索 SHALL 使用 pgvector 距离排序 + `LIMIT top_k`（暴力 top-K）；**SHALL NOT** 在本 change 创建 HNSW 或 IVFFlat 向量索引。

#### Scenario: 无 ANN migration

- **WHEN** 检查 `alembic_ai/002` revision
- **THEN** SHALL NOT 包含 `USING hnsw` 或 `USING ivfflat` 于 `embedding` 列

### Requirement: Query embedding via infra embedder

检索 **SHALL** 使用 `get_embedder()` 将 query 转为向量后再查询 PG；**SHALL NOT** 硬编码 embedding 维度。

#### Scenario: query embed 维度校验

- **WHEN** `EMBEDDING_DIMENSION=1024` 且执行检索
- **THEN** query 向量长度 SHALL 为 1024

### Requirement: Infra session factory for retrieval reads

检索读路径 **SHALL** 使用 `get_ai_session_factory()`；**SHALL NOT** 在 retrieval 模块新建 PG engine。

#### Scenario: integration 测试经 infra session 检索

- **WHEN** integration 测试调用 `retrieve_chunks`
- **THEN** SHALL 通过 infra 提供的 AI session 执行 PG 查询并成功返回

### Requirement: Change 2 retrieval tests exclude RAGAS

检索（ACL / smoke / `product_id` 过滤）测试 SHALL 覆盖查询语义；**SHALL NOT** 要求 RAGAS、`context_recall`、faithfulness 或黄金测试集 Hit@K 作为检索测或默认 `task ci` 的必过门禁。`ragas` SHALL NOT 作为检索模块或默认 CI 的必装依赖。离线评测跑道（`ai-ragas-eval`）SHALL 使用可选依赖组，且 SHALL 以 `retrieve_chunks` 为检索入口。

#### Scenario: CI 检索测不依赖 ragas 包

- **WHEN** 默认 CI / `tests/ai` 下检索 integration 运行
- **THEN** SHALL NOT 将 `ragas` 列为本路径必需依赖

#### Scenario: 评测检索入口仍是 retrieve_chunks

- **WHEN** 离线评测 adapter 执行检索
- **THEN** SHALL 调用 `retrieve_chunks`
- **AND** SHALL NOT 改用 LangChain Retriever / Retrieval Chain 作为检索实现

### Requirement: No LangChain retriever for ACL search

系统 SHALL NOT 使用 LangChain `BaseRetriever`、`VectorStoreRetriever` 或 Retrieval Chain 作为检索实现；检索逻辑 SHALL 位于 `app/ai/rag/retrieval/` 自研 repository。

#### Scenario: 检索代码不依赖 langchain 包

- **WHEN** 检查 `app/ai/rag/retrieval/` 模块 import
- **THEN** SHALL NOT import `langchain` 作为检索实现依赖
