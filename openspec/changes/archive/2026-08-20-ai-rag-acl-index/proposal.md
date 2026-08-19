## Why

Change 1（`infra-ai-pgvector`）已交付 PG + Embedder + 双 Alembic 管道，但尚无**多源商品语料索引**与**按 `shop_id` 隔离的向量检索**。没有这一层，Change 3 智能客服（`ai-support-agent`）的知识类意图无法工作（检索漏店、跨店泄露均违反 ADR-007）。

本 change 是 v2.0.0 AI MVP 的第二块：**多源语料（catalog 商品文本 + media 商家商品文档）→ 统一中间表示 → chunk → embed → pgvector → ACL 检索**。

语料边界依据（信息-来源映射）：商品描述/参数**无结构化参数表**（Product 模型仅 name/description/price/stock），信息主体是文本形态（description 字段 + media 文档）→ 进语义检索语料；price/stock 等交易属性有结构化源 → **不进语料**，由 Change 3 事实类意图经 Tool 直查业务域。

## What Changes

- 新增 **`app/ai/rag/`** 模块（对齐 architecture.md AI 域分层）：`chunking`、`indexing`、`retrieval`、IR schema、`product_embedding_chunks` ORM（继承 infra `AiBase`）
- 新增 **`alembic_ai/002_*`**：`product_embedding_chunks` 表（`vector(1024)`、`UNIQUE(shop_id, product_id, document_id, chunk_index)`、`source_kind`）
- 新增 **media 域商品-文档关联**：`MediaAsset` 加 `product_id`（可空，无 FK，应用层校验），`source_kind=media_document` 语料依赖此关联；chunk 的 ACL 键（shop_id）单一事实源为商品归属（不冗余到 MediaAsset）
- 新增 **media 解析 adapter**：商品文档（PDF/TXT）→ 文本（pymupdf，新依赖）；OCR 明确不做（边界）
- 新增 **统一中间表示（IR）**：`Document{ document_id, shop_id, product_id, source_kind, content_text, meta }`——多源收敛点，IR 之后单管线（chunk→embed→存→检索）
- 新增 **Task 批量 reindex**：`ai:reindex-shop`、`ai:reindex-product`、`ai:reindex-document`（delete-then-insert per document）
- 新增 **catalog 跨域只读接口**：`ProductRagSource` + `list_products_for_rag_indexing`（供 ai 索引拉取已上架商品文本）
- 新增 **ai 域公开 service**：`retrieve_chunks(shop_id, query, top_k)` → `RetrievedChunk`（Change 3 客服 agent 的知识类意图 handler 消费；空 query 返空、top_k 上限、score=余弦距离升序）；`delete_product_chunks` / `delete_document_chunks(source_kind, document_id)`（**ai 域内部接口**，本 change 无业务域调用方——下架/删附件清理由 reindex 承担）
- **检索 ACL**：强制 `WHERE shop_id = ?`；MVP 暴力 top-K（不建 HNSW/IVFFlat）
- **架构决策**：不采用 LangChain VectorStore / Retrieval Chain（见 design D1）；RAGAS 评测留给 Change 3；本 change 仅 ACL + 多源 smoke 检索测试

## Non-goals

- **不做** LangChain VectorStore、RetrievalQA、`create_retrieval_chain` 等编排（见 design D1）
- **不做** RAGAS / 黄金集 Hit@K / faithfulness 离线评测（Change 3 智能客服评测基线）
- **不做** 消费层：意图识别、客服 agent、LLM 生成、support 消息路由（Change 3）；本 change 只交付检索能力
- **不做** 商品 write 路径自动索引、Outbox、Celery 异步索引（改商品/文档后须手动/CI reindex；自动同步见 ADR-009）
- **不做** OCR（图片型 PDF 文档化边界）；**不做** Word（.docx）解析（MVP 仅 PDF/TXT，Word 按真实商家上传数据后置）
- **不做** 政策/FAQ 等其它语料源（`source_kind` 预留；Change 4 语料源扩展）
- **不做** ANN 索引（HNSW/IVFFlat）、rerank、混合检索
- **不做** 关店 purge 向量；**不做** `content_hash` 增量 diff 字段
- **不做** infra 层变更（复用 Change 1 的 `get_ai_session_factory()` + `get_embedder()`）

## Capabilities

### New Capabilities

- `ai-rag-indexing`：多源语料（catalog_text + media_document）摄入、IR、chunking、embed、PG upsert、Task reindex、删商品/文档清理 chunk
- `ai-rag-retrieval`：`shop_id` ACL 向量检索、`retrieve_chunks` 公开 service 契约（无 HTTP）

### Modified Capabilities

- `catalog-products`：新增跨域只读 `ProductRagSource` 与 `list_products_for_rag_indexing`（chunk 清理由 reindex 承担，catalog 不调用 ai）
- `media-storage`：`MediaAsset` 新增 `product_id`（可空，无 FK，应用层校验；商品-文档关联）

## Impact

| 域 / 系统 | 影响 |
|-----------|------|
| **ai**（新建） | `app/ai/rag/` 模块、AI 库 migration 002、reindex Task、integration 测试 |
| **catalog** | `schemas.ProductRagSource`、`product_service.list_products_for_rag_indexing`；下架清理由 reindex 承担（catalog 不调用 ai） |
| **media** | `MediaAsset` 加 `product_id` 列（无 FK）+ migration；新增商品文档查询/文件读取接口（供 ai 解析） |
| **infra** | 无代码变更；消费既有 `AiBase` / embedder / session factory |
| **Taskfile** | 新增 `ai:reindex-shop`、`ai:reindex-product`、`ai:reindex-document` |
| **依赖** | `pymupdf`（PDF/TXT 解析）新增 |
| **tests** | `tests/ai/` 多源 chunking、ACL 检索、reindex smoke；catalog/media 跨域 mock |
| **下游** | Change 3 智能客服：知识类意图 handler 消费 `retrieve_chunks`；事实类意图走 Tool；Change 4 扩展新 `source_kind` |
