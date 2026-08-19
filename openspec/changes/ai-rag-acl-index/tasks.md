## 1. TDD 红：失败测试

- [x] 1.1 新增 `tests/ai/test_chunking.py`：catalog 策略（单/多 chunk、header、空 description）+ media 策略（段落切分、超长硬切）（红）
- [x] 1.2 新增 `tests/ai/test_parsing.py`：PDF/TXT 解析 smoke（mock 文件）（红）
- [x] 1.3 新增 `tests/ai/test_indexing_integration.py`：reindex 单商品（catalog_text + media_document）→ PG 有 chunk 行（红）
- [x] 1.4 新增 `tests/ai/test_retrieval_acl_integration.py`：两店各 reindex 双源 → shop A query 不返回 shop B（红）
- [x] 1.5 新增 `tests/catalog/test_product_rag_source.py`：`list_products_for_rag_indexing` 仅已上架、shop 过滤（红）
- [x] 1.6 新增 `tests/media/test_asset_product_link.py`：`MediaAsset` 写入 `product_id` 关联 + 非法 UUID 拒绝（存在性校验在 ai 域 reindex，见 §1.3）（红）
- [x] 1.7 下架商品 reindex 清理测试：`is_published=false` 后 reindex → PG 无该 product chunk（红）

## 2. media 商品-文档关联

- [x] 2.1 media 域 migration：`media_assets` 加 `product_id`（可空，**无 FK**，普通列 + 索引；**不加** `shop_id`——chunk ACL 键单一事实源为商品归属）
- [x] 2.2 `app/media/schemas.py` + service：上传商品文档时写入关联；按 product 查询文档接口（纯 product_id 查询，无店级过滤）；确认/复用单资产查询接口（供 ai 域 orphan 逐条校验附件存在性）
- [x] 2.3 跑绿 §1.6

## 3. catalog 跨域只读 DTO

- [x] 3.1 `app/catalog/schemas.py` 增加 `ProductRagSource`（`product_id`、`shop_id`、`name`、`description`、`price`（元数据，不进语料）、`is_published`）
- [x] 3.2 `product_service.list_products_for_rag_indexing(shop_id: str | None)` + repository 查询（仅 `is_published=True`）
- [x] 3.3 跑绿 §1.5

## 4. AI 库 migration 与 ORM

- [x] 4.1 `app/ai/rag/models/product_embedding_chunk.py`（继承 `AiBase`；含 `document_id`、`source_kind`）
- [x] 4.2 `alembic_ai/versions/002_product_embedding_chunks.py`（`vector(1024)`、`UNIQUE(shop_id, product_id, document_id, chunk_index)`）
- [x] 4.3 `pyproject.toml` 新增 `pymupdf`
- [x] 4.4 `tests/conftest.py`（若需）：ai 模块 import / session 与现有 integration 纪律对齐
- [x] 4.5 `devbox run -- task migrate:ai` 验证 002

## 5. IR 与 chunking

- [x] 5.1 `app/ai/rag/schemas.py`：`DocumentIR`、`ProductChunkDraft`、`RetrievedChunk`、`ReindexStats`
- [x] 5.2 `app/ai/rag/chunking.py`：`split_document_to_chunks`（catalog_text 短文本 / media_document 段落切分）+ Settings `RAG_CHUNK_MAX_CHARS`（默认 800）
- [x] 5.3 跑绿 §1.1

## 6. media 解析 adapter

- [x] 6.1 `app/ai/rag/parsing.py`：PDF（pymupdf）/ TXT → 文本；解析失败记日志并跳过（不阻塞 reindex）
- [x] 6.2 `app/ai/rag/indexing/service.py`：media 文档拉取（调 media service 按 product 取文档 + 文件读取）
- [x] 6.3 跑绿 §1.2

## 7. indexing 实现

- [x] 7.1 `app/ai/rag/indexing/repository.py`：delete_by_document、bulk_insert、list_documents_for_shop（扫 orphan）
- [x] 7.2 `app/ai/rag/indexing/service.py`：`reindex_shop`、`reindex_product`、`reindex_document`（delete-then-insert per document；catalog + media 双源）
- [x] 7.3 `app/ai/service.py`（或等价门面）：`delete_product_chunks(product_id)`、`delete_document_chunks(source_kind, document_id)`（ai 域内部接口，无业务域调用方）
- [x] 7.4 reindex-shop orphan 扫描：按商品上架状态清理下架商品 chunk；`source_kind=media_document` 从 PG 反枚举 document_id → 经 media 单资产查询逐条校验附件存在性 → 不存在则删 chunk（业务域零 ai 依赖，无 catalog/media → ai 调用）
- [x] 7.5 跑绿 §1.3、§1.7

## 8. retrieval 实现

- [ ] 8.1 `app/ai/rag/retrieval/repository.py`：`vector_search(shop_id, embedding, top_k)` 强制 shop 过滤
- [ ] 8.2 `app/ai/rag/retrieval/service.py` + ai 门面：`retrieve_chunks`（返回 `RetrievedChunk` 含 `document_id`）
- [ ] 8.3 跑绿 §1.4

## 9. Task CLI

- [ ] 9.1 `app/ai/jobs/reindex_cli.py` + Taskfile `ai:reindex-shop` / `ai:reindex-product` / `ai:reindex-document --source-kind --document-id`（deps `pg:up`）
- [ ] 9.2 README 片段：改商品/传文档后须 reindex；示例 devbox 命令

## 10. 收尾与演示

- [ ] 10.1 `devbox run -- task ci` 全绿
- [ ] 10.2 演示：`ai:reindex-shop`（双源）→ `retrieve_chunks` 命中本店 chunk；跨店 ACL 单测/集成绿
- [ ] 10.3 `uv run ruff check .` 与 `task format:check` 通过
