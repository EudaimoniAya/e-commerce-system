## Context

Change 1（`infra-ai-pgvector`，已 archive）交付：

- `app/infra/ai_database.py`：`AiBase`、async PG engine/session、`get_ai_session_factory()`、`reset_ai_engine()`
- `app/infra/embedder.py`：`Embedder` 协议、`MockEmbedder`、`get_embedder()`、维度 fail-fast（1024）
- `alembic_ai/001`：`vector` 扩展 + `_infra_ai_migration_smoke`（`vector(1024)`）
- readiness 三库、Task `migrate:ai` / `migrate:all`、`task ci` deps 含 `pg:up`

Change 1 design §13 约定：后续 **SHALL 仅** 使用 `get_ai_session_factory()` + `get_embedder()`；业务向量表由 Change 2 的 `alembic_ai/002` 创建，维度 **SHALL** 与 001 一致（1024）。

架构约束（ADR-001 / ADR-007 / 跨域纪律）：

- MySQL 业务库为写源；PG 为 AI 读库（向量 + chunk 文本）
- ai 域 **不得** import 业务域 ORM/repository；索引时经业务域**数据提供接口**（catalog DTO / media 文件接口）
- catalog 下架/删除后的 chunk 清理由 ai 域 reindex 语义承担（业务域零 ai 依赖，无 catalog→ai 调用）
- Change 3 客服 agent **仅**通过 `retrieve_chunks()` 消费检索，不直连 PG；support 域不 import ai（依赖方向 ai→support→infra）

**语料边界依据（信息-来源映射）**：Product 模型无结构化参数表（仅 name/description/price/stock），商品信息主体是文本形态（description + media 文档）→ 语义文本进检索语料；交易属性（price/stock）有结构化源且易变 → **不进语料**，由 Change 3 事实类意图经 Tool 直查业务域。语义文本进语料、交易属性留业务域——与 backendProject 早期设计（核心属性同步 AI 上下文 / 交易属性业务独有）一致。

**AI 域分层（architecture.md §7 对齐）**：本 change 的 chunking/indexing/retrieval 落在 `app/ai/rag/`（客服场景能力，MVP 单消费者）；LLM gateway / trace / guardrails / memory 为 AI 共享底座（Change 3 涉及）；本 change 不触碰共享底座。

路线图：

```text
✅ Change 1  infra-ai-pgvector
▶ Change 2  ai-rag-acl-index（本 change）：多源语料管线 + ACL 检索（RAG 意图的底层能力）
  Change 3  ai-support-agent：智能客服骨架（意图识别 + 意图注册表 + 首批 handler：
            知识类走 RAG / 事实类走 Tool / 转人工）+ 评测基线
  Change 4  ai-rag-source-extend：语料源扩展（政策文档等新 source_kind）
```

## Goals / Non-Goals

**Goals:**

- 可演示闭环：Task reindex 店铺语料（catalog 文本 + media 文档）→ PG 有 chunk 行 → `retrieve_chunks(shop_id, query)` 返回 top-K 且 **不跨店**
- `product_embedding_chunks` 表（AI 域 ORM 继承 `AiBase`）；`alembic_ai/002`（含 `document_id`、`source_kind`）
- 多源语料：`catalog_text`（name/description，price 仅元数据）+ `media_document`（商家上传 PDF/TXT 解析文本）
- 商品-文档关联：`MediaAsset` 加 `product_id`（无 FK，应用层校验；media migration）
- 统一中间表示 IR：多源摄入后收敛为 `Document`，IR 之后单管线
- Task 批量 reindex：`ai:reindex-shop` / `ai:reindex-product` / `ai:reindex-document`（delete-then-insert per document）
- 对 Change 3 暴露稳定 DTO：`RetrievedChunk`（score、content_text、product_id、chunk_index、document_id、shop_id）
- TDD：chunking 单测（两策略）+ integration ACL smoke + 多源 reindex smoke

**Non-Goals:**

- LangChain VectorStore / Retrieval Chain / LC Retriever（见 Decision 1）
- RAGAS、黄金集 Hit@K、Generator 隔离评测（Change 3 评测基线）
- 消费层：意图识别、客服 agent、LLM 生成、support 消息路由（Change 3）
- 商品 write 自动索引、Outbox、Celery（ADR-009 后置）
- OCR（图片型 PDF）、Word(.docx) 解析（按真实数据后置）
- 政策/FAQ 等新语料源（Change 4）；HNSW/IVFFlat ANN；rerank
- `content_hash` 增量 diff；关店 purge；HTTP reindex API
- infra 层变更；AI 共享底座（gateway/trace/guardrails/memory）变更

## Decisions

### 1. 不采用 LangChain 向量层与 Retrieval Chain

**决策**：索引、embed、PG CRUD、ACL 检索 **全部自研** 于 `app/ai/rag/`；**不** 引入 LangChain `VectorStore`、`PGVector` wrapper、`RetrievalQA` / `create_retrieval_chain`。

**理由（项目内）**：

| 风险 | 说明 |
|------|------|
| ACL 易散 | LC Retriever 默认按 collection / filter 检索；`shop_id` 强制过滤须 monkey-patch metadata filter 或自定义 Retriever，逻辑藏在 Chain 内，违反「检索 + ACL 一眼可见」 |
| 跨域纪律 | LC VectorStore 常鼓励「Document loader 直连 DB」；与「业务域数据提供接口 → IR → ai chunk」冲突 |
| reindex 语义 | 本 change 为 per-document delete-then-insert + `UNIQUE(shop_id, product_id, document_id, chunk_index)`；LC upsert / delete 语义不透明 |
| 评测黑盒 | Change 3 需 Retriever 单独评测（RAGAS `context_recall`）；LC Chain 把 embed + retrieve + merge 打包，faithfulness 低时难归因 |

**理由（社区 / HN 常见批评，与本项目一致处）**：过度抽象（API 漂移）、隐式行为（Document merge / score 归一化 / callback 链）、依赖膨胀。

**仍可在 Change 3 局部使用 LC 的场景**：LLM 调用 wrapper、PromptTemplate——但检索上下文 **MUST** 来自 `retrieve_chunks()` 返回值，而非 LC Retriever。

### 2. 语料边界：双源并列，交易属性不进语料

**决策**：

- 语料源两类并列（`source_kind` 路由键，非"先 catalog 后扩展 media"）：
  - `catalog_text`：已上架商品的 `name` + `description`（category 名可并入 header）；price **仅元数据传递，不进 chunk 文本**
  - `media_document`：商家上传的商品相关文档（PDF/TXT 解析文本），依赖 `MediaAsset.product_id` 关联
- **不进语料**：price、stock、status 等交易属性——有结构化源、易变、embedding 对数值不敏感；由 Change 3 事实类意图经 Tool 直查业务域
- 每个商品可以同时有 `catalog_text` 与多个 `media_document` 语料

**理由**：商品参数无结构化表（信息-来源映射）；文本形态只能文本检索；交易属性走确定性查询（防 stale + 防幻觉）。

### 3. 商品-文档关联：MediaAsset 加 product_id（无 FK、无 shop_id 冗余）

**决策**：`MediaAsset` **新增** `product_id`（可空，**无外键约束**，普通列 + 索引）列（media 域 migration）；上传时 media 仅做 UUID 格式校验，**product 存在性/归属校验由 ai 域 indexing 承担**（reindex 时经 catalog 只读接口比对已上架商品，无效 product_id 的文档跳过并记日志——与 orphan 清理语义复用）。**不冗余 `shop_id`**——chunk 的 ACL 键（shop_id）单一事实源为**商品归属**（indexing 时经 catalog 获取），避免 MediaAsset 与商品归属不一致造成跨店泄露；且无 FK 避免外键 RESTRICT 阻塞商品侧生命周期。

**校验位置的理由**：media 域不可反向依赖 catalog（`catalog → media` 依赖已存在，反向校验成环）；media 的 `count_references` 先例是"查本域被谁引用"，不构成"跨域读存在性"的合法先例。校验后置到消费方（ai 域）是唯一无环路径，且复用 reindex 的无效文档清理语义。

**备选（未采用）**：独立 `product_documents` 表——多一跳；media-attach 引用——attach 实体无 product 语义；`shop_id` 冗余列——多一个需与商品保持一致的事实源，跨店泄露风险（ADR-007）。MVP 直接加列最简。

### 4. 文档解析管线：ai 域 rag 内部，MVP 仅 PDF/TXT

**决策**：PDF/TXT → 文本的解析逻辑放 **`app/ai/rag/parsing.py`**（单文件，RAG 是解析的唯一消费者，MVP）；依赖新增 `pymupdf`；media 域只提供原始文件读取（storage 层已有）。

**边界**：OCR（图片型 PDF）**不做**（文档化边界）；Word(.docx) **不做**（按真实商家上传数据后置）。若未来出现第二个「文件→文本」消费者（媒体预览/全文搜索），将解析提升至 media 域（演进路径，非本 change）。

### 5. 统一中间表示 IR：多源收敛点

**决策**：所有源经各自 adapter 后收敛为 `DocumentIR`：

```text
DocumentIR { document_id, shop_id, product_id, source_kind, content_text, meta }
- catalog_text : document_id = product_id（一商品一条文本源）
- media_document: document_id = 附件 UUID（一商品多文档）
```

IR 之后为单管线（chunk → embed → 存 → 检索），多源复杂度隔离在摄入层（各源一个 adapter）。

**`document_id` 命名空间**：`catalog_text` 与 `media_document` 的 document_id 共享同一列但**命名空间不同**（product_id vs 附件 UUID）。所有按 document 定位的接口（`delete_document_chunks`、`ai:reindex-document`）**MUST** 携带 `source_kind` 消歧，**SHALL NOT** 仅凭裸 UUID 定位。

### 6. Chunking：两策略，按 source_kind 路由

**决策**：

- `catalog_text`：header（name）+ description，短文本单 chunk（超 `RAG_CHUNK_MAX_CHARS` 按段落/硬切）
- `media_document`：按段落（`\n\n`）切分；长文档章节感知优先；每 chunk 携带 document_id + chunk_index
- `RAG_CHUNK_MAX_CHARS`（Settings，默认 800，可 env 覆盖）

### 7. 表结构：document_id 维度

**决策**：`product_embedding_chunks`（`alembic_ai/002`）：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | |
| `shop_id` | UUID NOT NULL | ACL 键 |
| `product_id` | UUID NOT NULL | catalog 商品 |
| `document_id` | UUID NOT NULL | catalog_text=product_id；media_document=附件 UUID |
| `chunk_index` | INT NOT NULL | 0..n-1 |
| `source_kind` | VARCHAR(32) NOT NULL | `catalog_text` \| `media_document` |
| `content_text` | TEXT NOT NULL | 检索展示与 Change 3 context |
| `embedding` | vector(1024) NOT NULL | 与 EMBEDDING_DIMENSION 一致 |
| `created_at` | TIMESTAMPTZ NOT NULL | 写入时间 |

约束：`UNIQUE(shop_id, product_id, document_id, chunk_index)`。索引（MVP）：`(shop_id)` B-tree 辅助过滤；**无** ANN 向量索引。

### 8. Reindex 语义：重建单位 = document

**决策**：per document delete-then-insert：

1. `DELETE FROM product_embedding_chunks WHERE shop_id=? AND product_id=? AND document_id=?`
2. 若源不可索引（商品下架/附件删除/解析失败）→ 净删
3. chunking → embed → INSERT

Task 命令：`ai:reindex-shop`（整店：catalog_text 全量 + media_document 全量，先扫 orphan——按商品上架状态与文档存在性校验清理下架商品/已删附件的 chunk）、`ai:reindex-product`（单商品全部 document）、`ai:reindex-document --source-kind --document-id`（单文档，source_kind 消歧）。

**清理语义（无业务域回调）**：商品下架（`PATCH is_published=false`，项目无 DELETE /products）、附件删除后的 chunk 清理**全部由 reindex 承担**——业务域 **SHALL NOT** 调用 ai service（避免 catalog→ai、media→ai 循环依赖，违反 CLAUDE.md 跨域纪律）。`delete_product_chunks` / `delete_document_chunks(source_kind, document_id)` 保留为 **ai 域内部接口**，供未来删除路径 / 事件驱动（ADR-009 Outbox）接线，本 change 无业务域调用方。清理存在 stale 窗口（下架/删附件后、下次 reindex 前），文档化接受（见 Risks）。

**运维约定**：改商品描述/上传新文档/下架商品/删除附件后须执行对应 reindex；README / Task help 写明。

### 9. ANN 索引：MVP 不建 HNSW/IVFFlat

**决策**：MVP 暴力 top-K（`<=>` + `ORDER BY` + `LIMIT`）；数据量上来后单独 change 加 ANN + benchmark。

### 10. ACL：强制 shop_id 过滤

**决策**：`retrieve_chunks` **MUST** 在 SQL 层 `WHERE shop_id = :shop_id`；**禁止** 仅按 product_id 或全局 top-K。理由：ADR-007 店铺隔离；Change 3 会话已绑定 shop。

### 11. 模块分层：对齐 architecture.md

```text
app/ai/
  rag/                        # 本 change 范围（客服场景能力，MVP 单消费者）
    schemas.py                # DocumentIR, ProductChunkDraft, RetrievedChunk, ReindexStats
    chunking.py               # 纯函数 split_document_to_chunks（两策略）
    parsing.py                # media 文档解析（pymupdf: PDF/TXT → 文本）
    indexing/
      service.py              # reindex_shop, reindex_product, reindex_document
      repository.py           # delete_by_document, bulk_insert, list_documents_for_shop
    retrieval/
      service.py              # retrieve_chunks
      repository.py           # vector_search(shop_id, embedding, top_k)
    models/
      product_embedding_chunk.py   # AiBase ORM
  jobs/
    reindex_cli.py            # Task 入口 argparse
  # 共享底座（Change 3 涉及，本 change 不实现）: gateway/ trace/ guardrails/ memory/
```

**升迁边界**：MVP 单消费者（Change 3 客服 agent 知识类意图）；未来多消费者（购物搭子等）出现时，将检索能力升迁至 AI 共享底座——本 change 不预建。

### 12. 调用类型区分：数据提供接口 vs 执行期 Tool 白名单

**决策**：本 change 的跨域调用为**管线期数据提供接口**（indexing → catalog DTO / media 文件接口），**不**走 Change 3 的执行期 tool 白名单（agents → 业务域 service）。两种调用类型分开声明：

```text
管线期（本 change）: indexing.service → catalog.product_service.list_products_for_rag_indexing   [数据提供]
                     indexing.service → media 文件读取/解析                                      [数据提供]
执行期（Change 3） : agents 知识类 → retrieve_chunks（ai 内部）                                    [tool 白名单外]
                     agents 事实类 → ai/tools/* → 业务域 service                                   [tool 白名单]
```

**理由**：reindex 是后台数据管线（非用户请求驱动），不构成 AI 对业务域的"执行调用"；门禁扩展（tool 白名单、禁 ORM）属 Change 3 范围。

**依赖方向（本 change 全部）**：ai → catalog / ai → media（数据提供接口）；**无任何业务域 → ai 调用**——业务域零 ai 依赖，模块依赖无环（当前代码库无业务域 import ai，本 change 不引入第一个）。

### 13. 检索契约：消费方 = Change 3 客服 agent

```python
async def retrieve_chunks(
    shop_id: str,
    query: str,
    top_k: int = 5,
) -> list[RetrievedChunk]: ...

async def delete_product_chunks(product_id: str) -> None: ...          # ai 域内部
async def delete_document_chunks(source_kind: str, document_id: str) -> None: ...  # ai 域内部
```

**`RetrievedChunk`**：`shop_id`, `product_id`, `document_id`, `chunk_index`, `content_text`, `score`（**float 余弦距离**，pgvector `<=>` 语义：**越小越相关**，结果按 score **升序**返回）。

**边界**：`query` 为空串/纯空白 → 返回 `[]`（不 embed 空文本）；`top_k` 默认 5、上限 20（超限钳制，不抛错）。

**消费方**：Change 3 客服 agent 的知识类意图 handler（ai 域内）。**NOT** support 域直调（业务域不 import ai）；support 仅作为消息入口，经 handler 注册表（Change 3）分派。

### 14. Change 3/4 定位（与架构路线对齐）

- **Change 3 `ai-support-agent`**：智能客服骨架——意图识别（NL 网关）+ 场景隔离意图注册表 + IntentController 生命周期 + 首批 handler（知识类走 `retrieve_chunks` / 事实类走 Tool / 转人工）+ 评测基线（黄金集 + 分层归因）。**RAG 只是其中一个意图的底层能力**，不是客服的全部
- **Change 4 `ai-rag-source-extend`**：语料源扩展（政策文档等新 `source_kind`），非"media 扩展"——media 文档已是本 change 主语料之一

### 15. 测试策略（本 change）

| 层级 | 内容 |
|------|------|
| 单测 | `chunking` 两策略（catalog 单/多 chunk；media 段落切分）、空 description、超长切段 |
| 单测 | `parsing`（PDF/TXT 提取 smoke，mock 文件） |
| integration | reindex 两店（catalog_text + media_document 各一）→ shop A query 不返回 shop B |
| integration | 删商品 → PG 无该 product chunk；删附件 → 该 document chunk 清空 |
| integration | 下架商品 reindex → chunk 被删 |
| **不做** | RAGAS、LLM judge、Hit@K 黄金集（Change 3） |

### 16. 异构数据一致性：单一事实源 + 派生数据 + 逻辑外键（ADR-011）

**决策**：本 change 的数据关联与一致性遵循 **ADR-011**（异构数据架构的数据一致性设计）：

- **单一事实源**：商品归属（shop_id）只在 MySQL `products` 权威存一份；`MediaAsset` 不冗余 shop_id（消除双事实源，防跨店泄露——ADR-007）
- **引用 vs 拷贝**：`MediaAsset.product_id` 是外键引用（指路，不复制属性），不是双事实源；引用正确性（写错）是脏数据问题，靠校验 + reindex 兜底
- **派生数据**：`product_embedding_chunks.shop_id` 等冗余是读副本缓存性质（PG 为派生层），一致性靠 **reindex 重建**，不靠数据库约束
- **逻辑外键**：`shop_id` / `product_id` / `document_id` 均为同值 UUID 列（跨库无法建 FK）；一致性完全由应用层维护（reindex 对比源状态 + orphan 扫描）
- **无 FK 判据**：`products` 无删除路径（下架走 PATCH）→ 指向它的 FK 价值 ≈ 0、只剩阻塞 → 不加；`media_assets` 有删除路径 → 既有 FK + `count_references` 保护（先例）
- **校验分层**：media 仅 UUID 格式校验（本域能力）；product 存在性/归属校验在 ai 域（数据消费者，唯一无环位置 + ACL 正确性前置）

**理由**：异构跨库无法用数据库约束管理一致性（无 FK/无事务）；此设计让"事实源永远一份（MySQL）、读侧缓存（PG）、关联靠引用、一致性靠重建"成为本 change 以及未来所有 MySQL→PG 同步场景的统一原则。详见 ADR-011。

### 17. RAG 前半段数据流（摄入 → IR → chunking，按文件/模块顺序）

多源语料在进入向量库之前的完整流动。数据形态逐段变化：**业务域 DTO → DocumentIR（ai 内部中间态）→ ProductChunkDraft（chunk 段）**。数据流脉络如下，按文件/模块流动顺序展开。

#### 17.1 media 源（非结构化文档，两步转换）

```text
app/media/service.py（MediaService，跨域数据提供接口）
  ├─ list_documents_by_product(product_id)
  │    → app/media/schemas.py::ProductDocumentInfo[]      # 元数据，不含正文
  │      （asset_id / content_type / storage_key / original_filename）
  └─ get_file_stream(asset_id) → (bytes, content_type)     # storage 原始字节，全量读入

app/ai/rag/indexing/service.py（ai 域 adapter）
  └─ media_documents_for_product(product_id, shop_id, media_service)
       ├─ 调 media service 拉元数据 + get_file_stream 读字节
       ├─ app/ai/rag/parsing.py::parse_document(content_type, bytes)
       │    → 纯文本（PDF 经 pymupdf；TXT 经 UTF-8；失败记日志返回空串 → 跳过该 document）
       └─ 构造 app/ai/rag/schemas.py::DocumentIR
            （source_kind=media_document, document_id=附件 UUID, content_text=整篇解析文本）
```

- **两步转换**：先拉元数据（`ProductDocumentInfo`，不含正文），再读字节 + 解析（`parse_document`）得到文本——正文不随元数据返回。
- **document_id 映射**：media_document → 附件 UUID（命名空间由 `source_kind` 消歧，design D5）。

#### 17.2 catalog 源（结构化表数据，一步组装）

```text
app/catalog/product_service.py
  └─ list_products_for_rag_indexing(shop_id, *, session)
       → app/catalog/schemas.py::ProductRagSource[]       # 结构化表行，自带文本字段
         （product_id / shop_id / name / description / price(仅元数据) / is_published）

ai 域 adapter（Task 7 reindex 内实现）
  └─ 组装 content_text = name + description（price 丢弃——design D2 不进语料）
       → 构造 DocumentIR
            （source_kind=catalog_text, document_id=product_id, content_text=组装文本）
```

- **一步转换**：`ProductRagSource` 自带 name/description 文本字段，直接组装；无「读字节 + 解析」环节。
- **price 仅元数据传递，不进入 content_text**（交易属性由 Change 3 事实类意图经 Tool 直查）。

#### 17.3 统一收敛与持久化边界

两个源都收敛为 `DocumentIR[]`（**内存中间态，不落库**）：

| DocumentIR 字段 | media 源 | catalog 源 |
|---|---|---|
| `document_id` | 附件 UUID | product_id |
| `content_text` | 解析后的整篇文档全文 | name + description 组装 |
| `source_kind` | `media_document` | `catalog_text` |
| `price` | 无 | 丢弃（design D2） |

`DocumentIR` 之后进入单管线（多源差异到此结束）：

```text
DocumentIR（整篇原文，内存中间态）
  → app/ai/rag/chunking.py::split_document_to_chunks(document, *, max_chars)
  → ProductChunkDraft[]（每段 ≤ RAG_CHUNK_MAX_CHARS=800，chunk_index 0..n-1）
  → get_embedder().embed_texts → INSERT product_embedding_chunks
```

**持久化边界**：落库的是**每段 chunk**（`document_id` / `content_text`段 / `source_kind` / `chunk_index` / `embedding`），不是整篇全文。

- `document_id` **必须落库**：溯源键（chunk 属于哪个文档），支撑 `delete_document_chunks`、检索展示关联、`UNIQUE(..., document_id, chunk_index)` 幂等。
- `content_text` 段 **必须落库**：检索返回原文给 LLM 当上下文（`RetrievedChunk.content_text`）；存的文本 = 被 embed 的文本，保证语义对齐。
- **DocumentIR 整篇全文只在内存存在一次**（切完即弃），不落库。

#### 17.4 全量 vs 流式（为什么摄入/解析用全量加载，而非流式）

摄入与解析采用**全量加载**（一次性读入 + 全量切分），不采用「边读边切」的流式管线，依据：

1. **文件大小上限保护**：media 上传上限 `media_max_size_bytes`（5MB）锁死单文档内存量级 → 全量加载无内存压力 → 流式收益（省内存）不存在 → 全量是最简正确实现。这是「上游约束简化下游」的设计。
2. **PDF 格式特性**：PDF 解析需完整文件（对象 / xref 随机访问），pymupdf 内部建完整文档结构；TXT 理论上可流式，但 5MB 上限下无收益。
3. **批量 embed**：`embed_texts` 批量接收 `list[str]`，全量切完 → 一次批量 embed → 批量 insert，优于逐段 N 次 API 调用。
4. **OCR 明确不做**（design D4）：OCR 比纯文本提取更重、更依赖全量（整页图像解码 + 识别），方向与流式相反；且是 Change 2 外边界。

**未来内存压力点**：真正会触发内存压力的是 **reindex 总量**（整店几千文档堆叠），而非单文档。Task 7 reindex 实现应**逐文档处理**——加载一个 `DocumentIR` → 切分 → embed → 写库 → 回收，再处理下一个；不做文档级批量堆叠。数据量上来后以「文档级流式」演进（非单文档流式）。

## Risks / Trade-offs

- **[Risk] 改商品/上传文档未 reindex → 检索 stale** → 文档 + Task help 强调；Change 3 可提示「知识库可能过期」
- **[Risk] media 文档解析健壮性**（PDF 变体/加密/乱码）→ 解析失败记日志并跳过该 document（reindex 统计报告）；OCR 边界文档化
- **[Risk] 暴力 top-K 随商品量变慢** → MVP 可接受；Change 4+ 评估 ANN
- **[Risk] MockEmbedder 与生产 embedding 行为不一致** → integration 测 ACL 与管道；换模型须 migration + 全量 reindex（Change 1 已文档化）
- **[Risk] 下架/删附件后至下次 reindex 前的 stale 窗口** → 文档化接受：`retrieve_chunks` 可能短暂返回已下架商品内容；README 注明「改商品/传文档/下架/删附件后须 reindex」
- **[Risk] PG 清理/写入失败（跨库无事务）** → MySQL 与 PG 间无分布式事务：indexing 失败记日志、reindex 重跑自愈；orphan 由 `ai:reindex-shop` 扫描兜底；业务写路径不受 PG 可用性影响（业务域零 ai 依赖）
- **[Risk] 跨域 import 违规** → CI `app-layer-discipline` + code review；本 change 调用类型（数据提供接口）在 design D12 声明

## Migration Plan

1. 合并前：Change 1 已在 main；本地 `devbox run -- task migrate:all`
2. apply 本 change：
   - media 域 migration（`MediaAsset` 加 `product_id`）→ `task migrate:business`
   - `alembic_ai/002` → `devbox run -- task migrate:ai`
3. 演示：`ai:reindex-shop` → pytest ACL 绿（两源 smoke）
4. 回滚：downgrade 002 + media migration；删除 `app/ai/rag/`；revert catalog/media service 扩展

## Open Questions

- `RAG_CHUNK_MAX_CHARS` 默认 800 是否需 apply 前用样例商品/文档微调 — **默认 800，apply 时样例验证**
- Word(.docx) 解析是否按真实商家上传数据提前 — **MVP 不做，数据驱动后置**
- `list_products_for_rag_indexing(None)` 是否限制 admin 专用 — **MVP Task 不校验 admin，文档标注仅运维使用**
- 项目无 `DELETE /products`（归档 spec 明令禁止，下架走 PATCH）——chunk 清理是否仅靠 reindex 的 stale 窗口可接受 — **MVP 接受（文档化），未来删除路径/Outbox 接线时引入 `delete_*_chunks` 调用方**
- `list_products_for_rag_indexing` 全平台无分页、`reindex_shop` 逐 product 调 media（N 次跨域调用）——**MVP 接受（数据量小），后续加游标/批量接口；本 change 不实现**
