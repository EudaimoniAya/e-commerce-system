## ADDED Requirements

### Requirement: Single-product reindex uses catalog get-by-id

`reindex_product` 与 `source_kind=catalog_text` 的单文档重建 SHALL 经 catalog `get_product_for_rag_indexing(product_id)` 解析语料源。**SHALL NOT** 为查找单个 `product_id` 调用 `list_products_for_rag_indexing(shop_id=None)`。`list_products_for_rag_indexing` 仅用于整店或全平台列举。

#### Scenario: reindex_product 不扫全平台

- **WHEN** 执行 `reindex_product(product_id)`
- **THEN** SHALL 调用 `get_product_for_rag_indexing`
- **AND** SHALL NOT 调用 `list_products_for_rag_indexing(shop_id=None)`

#### Scenario: 未上架单商品净删

- **WHEN** `get_product_for_rag_indexing` 返回 `None` 后执行 `reindex_product`
- **THEN** PG SHALL NOT 含该 `product_id` 的 chunk 行

### Requirement: source_kind named constants

系统 SHALL 在 `app/ai/rag/schemas.py` 定义 `catalog_text` 与 `media_document` 的命名常量。indexing、chunking 与 reindex CLI 的 `source_kind` 比较 / argparse choices SHALL 使用这些常量，**SHALL NOT** 在上述模块使用游离字面量。

#### Scenario: chunking 使用 schemas 常量

- **WHEN** 检查 `app/ai/rag/chunking.py` 对 `source_kind` 的分支
- **THEN** SHALL 引用 `app.ai.rag.schemas` 中的命名常量
- **AND** SHALL NOT 出现独立的 `"media_document"` / `"catalog_text"` 字面量比较

## MODIFIED Requirements

### Requirement: Cross-domain data-provider interfaces only

ai 域 indexing **SHALL** 通过业务域**数据提供接口**获取语料：catalog 经 `list_products_for_rag_indexing`、`get_product_for_rag_indexing` 与 `ProductRagSource` schema；media 经商品文档查询/文件读取接口（`MediaService` 由 `app.ai.deps` 装配后传入，SHALL NOT 在 indexing service 内从 `app.media.deps` 自装配）。**SHALL NOT** import 业务域 ORM 或 repository。

#### Scenario: reindex_shop 调用 catalog service

- **WHEN** `reindex_shop(shop_id)` 执行
- **THEN** SHALL 调用 catalog 只读 service 获取该店已上架商品列表
- **AND** SHALL 对每个返回的 `ProductRagSource` 执行 IR → chunking → embed

#### Scenario: reindex_shop 拉取 media 文档

- **WHEN** `reindex_shop(shop_id)` 执行
- **THEN** SHALL 先经 catalog 获取该店已上架商品列表，再按各 `product_id` 经传入的 `MediaService` 获取关联文档并解析、切分、embed（media 接口为纯 product_id 查询，不做店级过滤）

### Requirement: Chunk cleanup via ai internal interfaces and reindex

chunk 清理由 ai 域 **reindex / orphan 扫描**承担。**SHALL NOT** 提供给业务域或未实现事件总线调用的门面删除 API（`app.ai.service.delete_*_chunks`）。商品下架、附件删除后的清理 SHALL 经 `ai:reindex-shop` / `ai:reindex-product` 的 orphan 扫描与文档存在性校验完成。业务域 SHALL NOT import ai。

#### Scenario: reindex-shop 清除下架商品 chunk

- **WHEN** 商品被下架（`is_published=false`）后执行 `ai:reindex-shop`
- **THEN** PG `product_embedding_chunks` SHALL NOT 含该 `product_id` 的 chunk 行

#### Scenario: reindex-shop 清除已删附件 chunk

- **WHEN** 关联商品文档的附件被删除后执行 `ai:reindex-shop`
- **THEN** PG SHALL NOT 含该已删附件的 `document_id` 行（orphan 扫描：从 PG 反枚举 `source_kind=media_document` 的 document_id → 经 media 单资产查询逐条校验存在性 → 不存在则删除对应 chunk；见 media-storage spec）
