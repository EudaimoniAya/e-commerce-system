## MODIFIED Requirements

### Requirement: Product RAG source read service

catalog 域 SHALL 提供跨域只读 schema `ProductRagSource` 与 service 方法 `list_products_for_rag_indexing`、`get_product_for_rag_indexing`，供 ai 域索引拉取商品文本语料（`source_kind=catalog_text`）；engagement/ordering 既有 DTO **SHALL NOT** 被 ai 域复用为索引语料源。`ProductRagSource` SHALL NOT 包含 `price`（价格不进语料，事实类意图经 catalog Tool 查 MySQL）。

#### Scenario: ProductRagSource 字段

- **WHEN** 调用 `list_products_for_rag_indexing` 且存在已上架商品
- **THEN** 每项 SHALL 含 `product_id`、`shop_id`、`name`、`description`（可 null）、`is_published`
- **AND** SHALL NOT 含 `price` 字段

#### Scenario: 按 shop_id 过滤已上架商品

- **WHEN** 调用 `list_products_for_rag_indexing(shop_id=<uuid>)`
- **THEN** SHALL 仅返回该 `shop_id` 且 `is_published=True` 的商品
- **AND** SHALL NOT 返回其它店铺或未上架商品

#### Scenario: 全平台已上架列表供运维 reindex

- **WHEN** 调用 `list_products_for_rag_indexing(shop_id=None)`
- **THEN** SHALL 返回全平台所有 `is_published=True` 的商品

#### Scenario: 按 product_id 取已上架语料源

- **WHEN** 调用 `get_product_for_rag_indexing(product_id)` 且该商品存在且 `is_published=True`
- **THEN** SHALL 返回对应 `ProductRagSource`（字段同 list 项）

#### Scenario: 未上架或不存在返回 None

- **WHEN** 调用 `get_product_for_rag_indexing(product_id)` 且商品不存在或 `is_published=False`
- **THEN** SHALL 返回 `None` 而非抛 HTTP 错误
