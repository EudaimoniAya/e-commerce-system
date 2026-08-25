# ai-domain-composition

## MODIFIED Requirements

### Requirement: AI composition root in deps.py

系统 SHALL 提供 `app/ai/deps.py`，仅含装配类函数。除既有 `build_media_service(session)` 外，本 change SHALL 增加 `build_llm_client()`、`build_prompt_loader()`、`build_buyer_turn_handler()`（名称可等价，须为普通函数）。CLI 与测试 SHALL 以普通函数调用装配函数。SHALL NOT 提供 `get_current_*` 解析类 deps。SHALL NOT 新增 AI HTTP router（`app/ai/router.py` 或等价 `/ai/*` 路由模块）。客服 HTTP 入口 SHALL 继续由 support 域提供。

#### Scenario: CLI 经 deps 传入 MediaService

- **WHEN** 执行 `reindex_product` / `reindex_shop` / `reindex_document`
- **THEN** 调用方 SHALL 先调用 `app.ai.deps` 的装配函数得到 `MediaService` 再传入
- **AND** `app/ai/rag/indexing/service.py` SHALL NOT 在缺省时自行构造 `MediaService`

#### Scenario: 无 AI router 与解析类 deps

- **WHEN** 检查 `app/ai/`
- **THEN** SHALL NOT 存在 `app/ai/router.py`（或等价 AI HTTP 路由模块）
- **AND** `app/ai/deps.py` SHALL NOT 定义 `get_current_*`

#### Scenario: 组合根装配客服依赖

- **WHEN** 检查 `app/ai/deps.py`
- **THEN** SHALL 能装配 LLM 客户端、提示词加载器与买家回合 handler，供 `main.py` 注册到 support Port 工厂
