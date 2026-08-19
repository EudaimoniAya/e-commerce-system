# ai-rag-retrieval

## Purpose

ai 域向量检索与店铺 ACL：对 pgvector 做 shop 隔离 top-K 检索，向 Change 3 智能客服（客服 agent 知识类意图 handler）暴露 `retrieve_chunks` service；本 change 无 public 检索 HTTP，不含 RAGAS 评测。

## Requirements

### Requirement: Shop-scoped vector retrieval ACL

系统 SHALL 在 PG 向量检索 SQL 中 **强制** `WHERE shop_id = :shop_id`；**SHALL NOT** 返回其它店铺的 chunk，即使其向量与 query 更相似。

#### Scenario: 跨店 query 不泄露

- **WHEN** PG 中存在 shop A 与 shop B 的商品 chunk，且对 shop A 执行 `retrieve_chunks(shop_id=A, query=...)`
- **THEN** 返回列表中每一行的 `shop_id` SHALL 等于 A
- **AND** SHALL NOT 含 shop B 的 `product_id` 或 `content_text`

#### Scenario: SQL 层 shop_id 过滤

- **WHEN** 检查 retrieval repository 生成的向量查询
- **THEN** SHALL 在 WHERE 子句包含与参数绑定的 `shop_id` 条件

### Requirement: Retrieve chunks service API

系统 SHALL 在 `app/ai/service.py`（或等价门面）提供 `retrieve_chunks(shop_id, query, top_k)` → `list[RetrievedChunk]`，供 **Change 3 客服 agent 的知识类意图 handler（ai 域内）** 调用；**SHALL NOT** 暴露 public HTTP 检索路由；**SHALL NOT** 由 support 域直接调用（业务域不 import ai，support 仅经 Change 3 handler 注册表分派）。

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

本 change 测试 SHALL 覆盖 ACL 与 smoke 检索；**SHALL NOT** 要求 RAGAS、`context_recall`、faithfulness 或黄金集 Hit@K 作为 Change 2 门禁。

#### Scenario: CI 不依赖 ragas 包

- **WHEN** Change 2 测试在 CI 运行
- **THEN** SHALL NOT 将 `ragas` 列为本 change 必需依赖

### Requirement: No LangChain retriever for ACL search

系统 SHALL NOT 使用 LangChain `BaseRetriever`、`VectorStoreRetriever` 或 Retrieval Chain 作为检索实现；检索逻辑 SHALL 位于 `app/ai/rag/retrieval/` 自研 repository。

#### Scenario: 检索代码不依赖 langchain 包

- **WHEN** 检查 `app/ai/rag/retrieval/` 模块 import
- **THEN** SHALL NOT import `langchain` 作为检索实现依赖
