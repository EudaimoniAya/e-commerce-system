## 1. TDD — 失败测试（红）

- [x] 1.1 扩展 `tests/support/`：
  - `results.py`：ConversationResult、MessageResult、MessageListResult、InboxListResult 等
  - `helper/support.py`：原子 HTTP helper（`get_buyer_conversation`、`post_buyer_message`、`list_buyer_messages`、`list_inbox`、`get_inbox_conversation`、`list_inbox_messages`、`post_shop_message`）
- [x] 1.2 编写 `tests/support/test_support_buyer_conversation.py`（GET 404 无会话、200 有会话、shop 404、401、403 禁自购）；不编写实现
- [x] 1.3 编写 `tests/support/test_support_buyer_messages.py`（POST lazy create 201、复用会话、GET messages ASC/404、closed 422、body/refs 校验、body 超长 422）；不编写实现
- [x] 1.4 编写 `tests/support/test_support_message_refs.py`（纯 product ref、跨 shop 422、未上架 201、order ref 422、refs>10 422、响应仅 ref_type/ref_id）；不编写实现
- [x] 1.5 编写 `tests/support/test_support_inbox.py`（inbox 本店隔离、updated_at DESC、last_message_preview、店主回复 201、closed 店可回复、非本店 404、无关用户 404）；不编写实现
- [x] 1.6 编写 `tests/support/test_support_cross_shop.py`（同买家两 shop 独立会话）；不编写实现
- [x] 1.7 `devbox run -- task db:up` 后跑新增 support 测试，确认失败（红）

## 2. catalog 跨域 service（绿 · 依赖）

- [ ] 2.1 `app/catalog/schemas.py` 新增 `ShopSupportContext`；`ShopService` 新增 `get_shop_for_support`、`validate_product_refs_for_shop`
- [ ] 2.2 可选：`tests/catalog/test_support_service.py` 覆盖 404/422/未上架允许；跑至绿

## 3. 迁移与 support ORM（绿 · 基础）

- [ ] 3.1 `app/support/models.py`：`SupportConversation`、`SupportMessage`；`alembic/env.py` 导入 support models
- [ ] 3.2 新增 migration `011`：`support_conversations`、`support_messages` 表、UNIQUE 与索引

## 4. support 域实现（绿）

- [ ] 4.1 `repository.py` + `schemas.py`（Request/Response DTO、Paginated alias）
- [ ] 4.2 `SupportService`：lazy create、买卖家发消息、inbox、鉴权 403/404、closed 规则、preview/updated_at bump；注入 `ShopService`
- [ ] 4.3 `deps.py` + `router.py`（买家 `/support/shops/*`、店主 `/support/inbox/*`）；`main.py` 注册 router
- [ ] 4.4 跑 support integration 测试至全绿

## 5. 文档与 CI

- [ ] 5.1 更新 `docs/architecture.md`（support 域、API 摘要、ADR-007 演进指针）
- [ ] 5.2 `devbox run -- task ci` 全绿（含 support integration + catalog service 测）
