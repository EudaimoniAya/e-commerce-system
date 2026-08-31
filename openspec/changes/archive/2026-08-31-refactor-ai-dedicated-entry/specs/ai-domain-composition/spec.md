# ai-domain-composition

## MODIFIED Requirements

### Requirement: AI composition root in deps.py

系统 SHALL 提供 `app/ai/deps.py`，以装配类函数为主。SHALL 提供 `build_media_service(session)`、`build_llm_client()`、`build_prompt_loader()`、`build_intent_controller()`（普通函数）。CLI 与测试 SHALL 以普通函数调用装配函数。客服 HTTP SHALL 由 `app/ai/router.py` 提供（`/ai/*`），router 调用 `build_intent_controller()`，SHALL NOT 经 support 模块级工厂注入。`app/ai/deps.py` SHALL NOT 定义 `get_current_*` 解析类（买家 id 由 router 使用 infra `get_current_user_id`）。

#### Scenario: CLI 经 deps 传入 MediaService

- **WHEN** 执行 `reindex_product` / `reindex_shop` / `reindex_document`
- **THEN** 调用方 SHALL 先调用 `app.ai.deps` 的装配函数得到 `MediaService` 再传入
- **AND** `app/ai/rag/indexing/service.py` SHALL NOT 在缺省时自行构造 `MediaService`

#### Scenario: 存在 AI router 且 deps 无 get_current_*

- **WHEN** 检查 `app/ai/`
- **THEN** SHALL 存在 `app/ai/router.py`（或等价 `/ai/*` 路由模块）
- **AND** `app/ai/deps.py` SHALL NOT 定义 `get_current_*`

#### Scenario: 组合根装配客服编排器

- **WHEN** 检查 `app/ai/deps.py`
- **THEN** SHALL 能装配 LLM 客户端、提示词加载器与 `build_intent_controller`
- **AND** `app/main.py` SHALL NOT 调用 `register_buyer_turn_handler_factory`
