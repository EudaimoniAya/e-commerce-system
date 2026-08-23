# ai-domain-composition

## Purpose

AI 域消费边界与组合根：`app/ai/deps.py` 为唯一装配点（不含 router / 解析类 deps）；AI 域 service 不自装配别域 deps；业务域 SHALL NOT import ai；不保留 `app/ai/service.py` 转发门面。

## Requirements

### Requirement: AI composition root in deps.py

系统 SHALL 提供 `app/ai/deps.py`，仅含装配类函数（至少 `build_media_service(session)`，返回 `MediaService`）。CLI 与测试 SHALL 以普通函数调用这些装配函数，再将依赖传入 indexing service。在 AI 域尚无 router 时，SHALL NOT 要求 FastAPI `Depends`，SHALL NOT 提供 `get_current_*` 解析类 deps，SHALL NOT 新增 AI HTTP router。

#### Scenario: CLI 经 deps 传入 MediaService

- **WHEN** 执行 `reindex_product` / `reindex_shop` / `reindex_document`
- **THEN** 调用方 SHALL 先调用 `app.ai.deps` 的装配函数得到 `MediaService` 再传入
- **AND** `app/ai/rag/indexing/service.py` SHALL NOT 在缺省时自行构造 `MediaService`

#### Scenario: 无 AI router 与解析类 deps

- **WHEN** 检查 `app/ai/`
- **THEN** SHALL NOT 存在 `app/ai/router.py`（或等价 AI HTTP 路由模块）
- **AND** `app/ai/deps.py` SHALL NOT 定义 `get_current_*`

### Requirement: AI service must not self-assemble foreign deps

`app/ai/**` 下除 `deps.py` 外的模块 SHALL NOT import 其他业务域的 `deps`（含 `app.media.deps.get_media_service`）。indexing service 的 `media_service` 参数 SHALL 为必传。

#### Scenario: indexing service 不含 _build_media_service

- **WHEN** 检查 `app/ai/rag/indexing/service.py`
- **THEN** SHALL NOT 存在 `_build_media_service` 或对 `app.media.deps` 的 import

#### Scenario: 下架净删不依赖 MediaService 逻辑

- **WHEN** `reindex_product` 对应商品未上架或不存在
- **THEN** SHALL 仅删除该 `product_id` 的 chunk 并返回统计
- **AND** service 内部 SHALL NOT 为该路径调用 media 列表/读文件接口

### Requirement: Business domains must not import ai

user / catalog / ordering / engagement / support / media 域模块 SHALL NOT import `app.ai` 下任何模块（含 service、schemas、deps）。

#### Scenario: catalog 无 app.ai import

- **WHEN** 检查 catalog 域模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块

#### Scenario: AST 拦截业务域 import ai

- **WHEN** 合成模块位于业务域且 `from app.ai.rag.retrieval.service import retrieve_chunks`
- **THEN** `check_app_layer_discipline` SHALL 报违规并 exit 1

#### Scenario: AST 拦截 AI service import media deps

- **WHEN** 合成模块路径为 `app/ai/rag/indexing/service.py` 且 import `app.media.deps`
- **THEN** `check_app_layer_discipline` SHALL 报违规并 exit 1

#### Scenario: AST 放行 AI deps 装配 media

- **WHEN** `app/ai/deps.py` import `app.media.deps.get_media_service`
- **THEN** `check_app_layer_discipline` SHALL NOT 因此报违规

### Requirement: No speculative AI facade module

系统 SHALL NOT 保留 `app/ai/service.py` 作为检索或删除的转发门面。检索入口 SHALL 为 `app.ai.rag.retrieval.service.retrieve_chunks`。

#### Scenario: 不存在 app.ai.service 门面

- **WHEN** 检查 `app/ai/service.py`
- **THEN** 该文件 SHALL NOT 存在（或 SHALL NOT 再导出 `retrieve_chunks` / `delete_product_chunks` / `delete_document_chunks`）
