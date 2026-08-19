# catalog-products (delta)

## ADDED Requirements

### Requirement: Product RAG source read service

catalog 域 SHALL 提供跨域只读 schema `ProductRagSource` 与 service 方法 `list_products_for_rag_indexing`，供 ai 域索引拉取商品文本语料（`source_kind=catalog_text`）；engagement/ordering 既有 DTO **SHALL NOT** 被 ai 域复用为索引语料源。

#### Scenario: ProductRagSource 字段

- **WHEN** 调用 `list_products_for_rag_indexing` 且存在已上架商品
- **THEN** 每项 SHALL 含 `product_id`、`shop_id`、`name`、`description`（可 null）、`price`（两位小数字符串，**仅元数据传递，不进索引语料**——保留供 Change 3 事实类意图经 Tool 查询时复用，本 change 不消费）、`is_published`

#### Scenario: 按 shop_id 过滤已上架商品

- **WHEN** 调用 `list_products_for_rag_indexing(shop_id=<uuid>)`
- **THEN** SHALL 仅返回该 `shop_id` 且 `is_published=True` 的商品
- **AND** SHALL NOT 返回其它店铺或未上架商品

#### Scenario: 全平台已上架列表供运维 reindex

- **WHEN** 调用 `list_products_for_rag_indexing(shop_id=None)`
- **THEN** SHALL 返回全平台所有 `is_published=True` 的商品

### Requirement: No chunk cleanup call from catalog

catalog 域 **SHALL NOT** import ai 域或调用 ai service（含 `delete_product_chunks`）——业务域不依赖 ai（CLAUDE.md 跨域纪律）。商品下架/删除后的 chunk 清理 **SHALL** 由 ai 域 reindex 语义承担（`ai:reindex-shop` 扫 orphan / 下架商品 reindex 清 chunk，见 ai-rag-indexing spec）。catalog 域**不提供** `DELETE /products`（归档 spec：商家经 `PATCH is_published=false` 下架），本 change 不新增删除路径。

#### Scenario: catalog 无 ai 依赖

- **WHEN** 检查 catalog 域模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块

#### Scenario: 下架商品清理由 reindex 承担

- **WHEN** 商品被 `PATCH is_published=false` 下架后执行 `ai:reindex-shop`（或 `ai:reindex-product`）
- **THEN** PG `product_embedding_chunks` SHALL NOT 含该 `product_id` 的 chunk 行
