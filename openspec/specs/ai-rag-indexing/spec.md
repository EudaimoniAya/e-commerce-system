# ai-rag-indexing

## Purpose

ai 域多源语料索引：catalog 商品文本（`catalog_text`）与 media 商品文档（`media_document`）经统一中间表示 IR → chunking → Embedder → 写入 PG `product_embedding_chunks`；Task 批量 reindex（per document）；删商品/删附件清理 chunk。为 Change 3 智能客服知识类意图提供语料，为 Change 4 新语料源预留 `source_kind`。

## Requirements

### Requirement: Product embedding chunks table

系统 SHALL 在 AI 读库（PostgreSQL）创建 ai 域表 `product_embedding_chunks`（ORM 继承 infra `AiBase`，模型位于 `app/ai/rag/models/`），通过 `alembic_ai/002` migration 管理；**SHALL NOT** 经 MySQL Alembic 创建。

#### Scenario: 表字段与约束

- **WHEN** 执行 AI 库 `upgrade head` 且 revision 002 已应用
- **THEN** 表 SHALL 含列：`id`（UUID PK）、`shop_id`、`product_id`、`document_id`（UUID）、`chunk_index`（INT）、`source_kind`（VARCHAR）、`content_text`（TEXT）、`embedding`（`vector(1024)`）、`created_at`（TIMESTAMPTZ）
- **AND** SHALL 存在唯一约束 `UNIQUE(shop_id, product_id, document_id, chunk_index)`

#### Scenario: embedding 维度与 infra 一致

- **WHEN** `EMBEDDING_DIMENSION=1024` 且 migration 002 已应用
- **THEN** `embedding` 列 SHALL 为 `vector(1024)`

### Requirement: Unified document IR before chunking

系统 SHALL 在 chunking 前将各源收敛为统一中间表示 `DocumentIR{ document_id, shop_id, product_id, source_kind, content_text, meta }`；`catalog_text` 的 `document_id` SHALL 等于 `product_id`；`media_document` 的 `document_id` SHALL 为附件 UUID。

#### Scenario: catalog 源生成 IR

- **WHEN** 对已上架商品的 `ProductRagSource` 执行摄入
- **THEN** SHALL 生成 `DocumentIR` 且 `source_kind=catalog_text`、`document_id=product_id`
- **AND** `content_text` SHALL 由 name + description 组装；**SHALL NOT** 包含 price

#### Scenario: media 源生成 IR

- **WHEN** 对已关联商品的 media 附件执行摄入
- **THEN** SHALL 生成 `DocumentIR` 且 `source_kind=media_document`、`document_id=附件UUID`
- **AND** `content_text` SHALL 为解析后的文档文本（解析失败时该 document SHALL 被跳过并计入 reindex 统计）

### Requirement: Media document parsing

系统 SHALL 在 `app/ai/rag/parsing.py` 提供 PDF/TXT → 文本解析（依赖 `pymupdf`）；解析失败 SHALL 记录日志并跳过该 document（不阻塞整店 reindex）。本 change **SHALL NOT** 实现 OCR 或 Word(.docx) 解析。

#### Scenario: PDF 解析成功写入文本

- **WHEN** 对有效 PDF 附件调用解析
- **THEN** SHALL 返回其文本内容（空页返回空串不抛错）

#### Scenario: 解析失败跳过不阻塞

- **WHEN** 某 document 解析抛错
- **THEN** reindex SHALL 跳过该 document、记录错误到 `ReindexStats`，并继续处理其余 document

### Requirement: Chunking by source kind

系统 SHALL 在 `app/ai/rag/chunking.py` 将 `DocumentIR` 转为有序 chunk 列表；`chunk_index` SHALL 从 0 递增；同一 document 的 chunk 数 SHALL 受 `RAG_CHUNK_MAX_CHARS`（默认 800）约束。

#### Scenario: catalog 短文本单 chunk

- **WHEN** `source_kind=catalog_text` 且 name+description 合并后不超过 `RAG_CHUNK_MAX_CHARS`
- **THEN** chunking SHALL 返回恰好 1 个 chunk，且 `chunk_index=0`
- **AND** `content_text` SHALL 含商品名与描述；**SHALL NOT** 含价格信息

#### Scenario: catalog 长文本多 chunk

- **WHEN** description 超过 `RAG_CHUNK_MAX_CHARS` 或含多个段落
- **THEN** chunking SHALL 返回多个 chunk，`chunk_index` 连续 0..n-1
- **AND** 首个 chunk SHALL 含商品名前缀

#### Scenario: media 文档段落切分

- **WHEN** `source_kind=media_document` 且文档含多段落
- **THEN** chunking SHALL 按段落切分为多个 chunk，`chunk_index` 连续 0..n-1

### Requirement: Index only published products with valid sources

系统 SHALL 仅对 `is_published=True` 的商品写入 chunk；对已下架、已删除商品或已删除附件对应的 document SHALL 删除其在 PG 中的全部 chunk。

#### Scenario: 已上架商品双源 reindex 写入 PG

- **WHEN** Task 对 `is_published=True` 的商品执行 reindex（含 catalog_text 与关联 media_document）
- **THEN** PG SHALL 存在该 `(shop_id, product_id)` 的至少一行 chunk（catalog_text 或 media_document，任一源可索引即成立）

#### Scenario: 下架商品 reindex 清除 chunk

- **WHEN** 对 `is_published=False` 的商品执行 reindex
- **THEN** PG SHALL NOT 存在该 `product_id` 的任何 chunk 行

### Requirement: Reindex delete-then-insert per document

系统 SHALL 对单个 document reindex 时先删除该 `(shop_id, product_id, document_id)` 全部既有 chunk，再插入新 chunk；**SHALL NOT** 使用 `content_hash` 增量 diff。

#### Scenario: 重复 reindex 不产生 duplicate

- **WHEN** 同一 document 连续执行两次 reindex 且源未变
- **THEN** PG 中该 document chunk 行数 SHALL 与第一次 reindex 相同
- **AND** SHALL NOT 违反 `UNIQUE(shop_id, product_id, document_id, chunk_index)`

### Requirement: Cross-domain data-provider interfaces only

ai 域 indexing **SHALL** 通过业务域**数据提供接口**获取语料：catalog 经 `list_products_for_rag_indexing` 与 `ProductRagSource` schema；media 经商品文档查询/文件读取接口。**SHALL NOT** import 业务域 ORM 或 repository。

#### Scenario: reindex_shop 调用 catalog service

- **WHEN** `reindex_shop(shop_id)` 执行
- **THEN** SHALL 调用 catalog 只读 service 获取该店已上架商品列表
- **AND** SHALL 对每个返回的 `ProductRagSource` 执行 IR → chunking → embed

#### Scenario: reindex_shop 拉取 media 文档

- **WHEN** `reindex_shop(shop_id)` 执行
- **THEN** SHALL 先经 catalog 获取该店已上架商品列表，再按各 `product_id` 经 media 只读接口获取关联文档并解析、切分、embed（media 接口为纯 product_id 查询，不做店级过滤）

### Requirement: Infra embedder and session factory only

ai 域 indexing **SHALL** 使用 `get_embedder()` 与 `get_ai_session_factory()`（或等价 infra API）访问 embedding 与 PG；**SHALL NOT** 在 ai 域新建独立 PG engine 池。

#### Scenario: embed_texts 写入 PG

- **WHEN** reindex 生成 N 个 chunk 文本
- **THEN** SHALL 调用 `get_embedder().embed_texts(texts)`（协议方法，本身批量接收 list）得到 N 个维度 1024 的向量并写入 PG

### Requirement: Task batch reindex commands

系统 SHALL 提供 Taskfile 命令 `ai:reindex-shop`、`ai:reindex-product`、`ai:reindex-document`，经 devbox 可执行；**SHALL NOT** 在商品/附件 write HTTP 路径自动触发索引。

#### Scenario: reindex-shop 索引整店双源

- **WHEN** 运维执行 `task ai:reindex-shop` 并传入有效 `shop_id`
- **THEN** 该店所有已上架商品的 catalog_text 与 media_document 语料 SHALL 在 PG 中有对应 chunk（或已被删除若无可索引语料）

#### Scenario: reindex-product 索引单商品全部文档

- **WHEN** 运维执行 `task ai:reindex-product` 并传入有效 `product_id`
- **THEN** SHALL 对该商品全部 document（catalog_text + 所有关联 media_document）执行 delete-then-insert

#### Scenario: reindex-document 索引单文档

- **WHEN** 运维执行 `task ai:reindex-document` 并传入有效 `--source-kind` 与 `--document-id`
- **THEN** SHALL 仅对该 `(source_kind, document_id)` 执行 delete-then-insert（`document_id` 命名空间由 `source_kind` 消歧）

### Requirement: Chunk cleanup via ai internal interfaces and reindex

chunk 清理由 ai 域内部接口承担：`delete_product_chunks(product_id)`（清该商品全部 document 的 chunk）与 `delete_document_chunks(source_kind, document_id)`（清单个 document 的 chunk）。**业务域 SHALL NOT 调用这些接口**（业务域不依赖 ai，见 catalog-products / media-storage delta spec）；商品下架、附件删除后的清理 **SHALL** 经 `ai:reindex-shop` / `ai:reindex-product` 的 orphan 扫描与文档存在性校验完成。`delete_*_chunks` 接口保留供未来删除路径 / 事件驱动（ADR-009 Outbox）接线。

#### Scenario: reindex-shop 清除下架商品 chunk

- **WHEN** 商品被下架（`is_published=false`）后执行 `ai:reindex-shop`
- **THEN** PG `product_embedding_chunks` SHALL NOT 含该 `product_id` 的 chunk 行

#### Scenario: reindex-shop 清除已删附件 chunk

- **WHEN** 关联商品文档的附件被删除后执行 `ai:reindex-shop`
- **THEN** PG SHALL NOT 含该已删附件的 `document_id` 行（orphan 扫描：从 PG 反枚举 `source_kind=media_document` 的 document_id → 经 media 单资产查询逐条校验存在性 → 不存在则删除对应 chunk；见 media-storage spec）

#### Scenario: delete_document_chunks 签名含 source_kind

- **WHEN** 调用 `delete_document_chunks(source_kind, document_id)`
- **THEN** SHALL 按 `(source_kind, document_id)` 定位并删除对应 chunk 行（`document_id` 命名空间由 `source_kind` 消歧：`catalog_text` 的 document_id=product_id、`media_document` 的 document_id=附件 UUID）

### Requirement: Source kind extensibility

系统 SHALL 在 `product_embedding_chunks.source_kind` 支持枚举值；本 change **SHALL** 写入 `catalog_text` 与 `media_document` 两类；**SHALL** 预留 schema 供后续 `source_kind`（Change 4 政策等）扩展，本 change 不实现其它 kind 的摄入逻辑。

#### Scenario: 双源 reindex 写入对应 source_kind

- **WHEN** 对 catalog 文本与 media 文档分别 reindex
- **THEN** 插入行的 `source_kind` SHALL 分别为 `catalog_text` 与 `media_document`

### Requirement: No LangChain vector store for indexing

系统 SHALL NOT 使用 LangChain `VectorStore`、`PGVector` 或 Retrieval Chain 作为索引写入路径；索引逻辑 SHALL 位于 `app/ai/rag/indexing/` 自研 service/repository。

#### Scenario: 索引代码不依赖 langchain 包

- **WHEN** 检查 `app/ai/rag/indexing/` 模块 import
- **THEN** SHALL NOT import `langchain` 或 `langchain_community` 作为索引实现依赖
