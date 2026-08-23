## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Shop-scoped vector retrieval ACL

系统 SHALL 在 PG 向量检索 SQL 中 **强制** `WHERE shop_id = :shop_id`；**SHALL NOT** 返回其它店铺的 chunk，即使其向量与 query 更相似。本要求描述的是查询时的店铺过滤，不是 MySQL↔pgvector 防腐层。

#### Scenario: 跨店 query 不泄露

- **WHEN** PG 中存在 shop A 与 shop B 的商品 chunk，且对 shop A 执行 `retrieve_chunks(shop_id=A, query=...)`
- **THEN** 返回列表中每一行的 `shop_id` SHALL 等于 A
- **AND** SHALL NOT 含 shop B 的 `product_id` 或 `content_text`

#### Scenario: SQL 层 shop_id 过滤

- **WHEN** 检查 retrieval repository 生成的向量查询
- **THEN** SHALL 在 WHERE 子句包含与参数绑定的 `shop_id` 条件

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
