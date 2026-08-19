# media-storage (delta)

## Purpose

media 域商品-文档关联：`MediaAsset` 新增 `product_id`（可空），使商家上传的商品文档可被 ai 域识别为 RAG 语料（`source_kind=media_document`）。**chunk 的 ACL 键（shop_id）单一事实源为商品**——本 change 不给 MediaAsset 冗余 shop_id，indexing 时经 catalog 按商品归属写入 chunk。

## ADDED Requirements

### Requirement: MediaAsset product association

系统 SHALL 在 `media_assets` 表新增 `product_id`（UUID，可空，**无外键约束**，普通列 + 索引），经 media 域 migration 管理；**SHALL NOT** 引入 FK 以避免阻塞商品侧生命周期（商品无 DELETE 路径，且外键 RESTRICT 会干扰未来演进）。

#### Scenario: 上传商品文档写入关联（仅格式校验）

- **WHEN** 商家上传商品相关文档且指定关联商品
- **THEN** `MediaAsset` 行 SHALL 记录 `product_id`
- **AND** media service SHALL 仅校验 `product_id` 为合法 UUID（格式错误返回 4xx）；**SHALL NOT** 跨域校验 product 存在性（media 不依赖 catalog——catalog→media 依赖已存在，反向校验会成环）

#### Scenario: product 存在性校验由 ai 域承担

- **WHEN** ai 域 `reindex_shop` 拉取商品文档时发现 `product_id` 不存在或商品未上架
- **THEN** SHALL 跳过该 document 并计入 `ReindexStats`（复用 orphan/无效文档清理语义，不阻塞整店 reindex）

#### Scenario: 未关联附件可空

- **WHEN** 上传非商品文档（如头像、通用素材）
- **THEN** `product_id` SHALL 为 NULL，不影响既有 media 行为

### Requirement: Product-scoped document read interface

media 域 SHALL 提供按 `product_id` 查询商品文档列表的只读接口（返回 `MediaAsset` 元数据 + 存储键），供 ai 域 indexing 拉取解析；**SHALL NOT** 暴露给 ai 域底层 storage 内部对象。**media 接口为纯 `product_id` 查询，不做店级过滤**（`MediaAsset` 无 `shop_id`，见 design D3）——店级隔离由 ai 侧 catalog 已上架商品列表保证（ADR-011 §6 校验沿消费方向）。

#### Scenario: ai reindex 拉取商品文档

- **WHEN** ai 域 `reindex_shop(shop_id)` 执行
- **THEN** SHALL 先经 catalog 获取该店已上架商品列表，再按各 `product_id` 经 media 只读接口获取关联文档（含 `asset_id`、`content_type`、`storage_key`、`original_filename`）
- **AND** media 接口 SHALL NOT 接收或依赖 `shop_id`（无店级过滤能力）

### Requirement: Single-asset existence query for orphan cleanup

media 域 SHALL 提供按 `asset_id` 查询单个附件的能力（复用既有单资产查询/详情接口），供 ai 域 reindex orphan 扫描校验「附件是否仍存在」；MVP **SHALL NOT** 新增批量接口（逐条查询，N 次调用可接受，见 design Open Questions）。

#### Scenario: orphan 校验附件存在性

- **WHEN** ai 域 `reindex_shop` 从 PG 反枚举 `document_id`（`source_kind=media_document`）且需校验附件是否仍存在
- **THEN** SHALL 经 media 单资产查询接口逐条校验；附件不存在（404）→ 删除对应 chunk 行

### Requirement: No chunk cleanup call from media

media 域 **SHALL NOT** import ai 域或调用 ai service（含 `delete_document_chunks`）——业务域不依赖 ai（CLAUDE.md 跨域纪律）。附件删除后的 chunk 清理 **SHALL** 由 ai 域 reindex 语义承担（`ai:reindex-shop` 扫 orphan / 商品级 reindex 时校验文档存在性，见 ai-rag-indexing spec）。

#### Scenario: media 无 ai 依赖

- **WHEN** 检查 media 域模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块

#### Scenario: 删附件后 orphan 由 reindex 兜底

- **WHEN** 商家删除已关联商品的附件后执行 `ai:reindex-shop`
- **THEN** PG `product_embedding_chunks` SHALL NOT 含已删除附件的 `document_id` 行
