# support-conversations

## Purpose

support 域店铺客服会话垂直切片：买家在 `shop_id` 管辖下与店铺咨询（lazy create、可引用本店商品）、店主 inbox 与回复、双方消息历史。表：`support_conversations`、`support_messages`（migration `011`）。跨域校验调用 `catalog.service.get_shop_for_support`、`catalog.service.validate_product_refs_for_shop`；禁止 import catalog ORM/repository。对齐 ADR-007，为 `ai-support-agent` 预留 `handler_mode`、`author_role`。

## Requirements

### Requirement: support_conversations and support_messages tables

系统 SHALL 在 **support 域** 拥有 `support_conversations` 与 `support_messages` 表（migration `011`，依赖当前 Alembic head）。SHALL NOT 声明跨域 SQLAlchemy relationship。

#### Scenario: support_conversations 表包含必需字段

- **WHEN** 查询 `support_conversations` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`shop_id`、`buyer_user_id`、`handler_mode`（`ai` \| `human`）、`last_message_preview`、`created_at`、`updated_at`
- **AND** SHALL 有 `UNIQUE(shop_id, buyer_user_id)`

#### Scenario: support_messages 表包含必需字段

- **WHEN** 查询 `support_messages` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`conversation_id`、`sender_role`（`buyer` \| `shop`）、`author_role`（`human` \| `ai`）、`body`（可空 TEXT）、`message_refs`（可空 JSON）、`created_at`

### Requirement: Message identity and handler_mode defaults

系统 SHALL 在每条消息上区分 `sender_role`（对话侧）与 `author_role`（撰写者）。会话 SHALL 含 `handler_mode` 表示当前 AI 是否参与（供前端展示与后续路由）。MVP 创建会话时 `handler_mode` SHALL 为 `human`；MVP 写入消息时 `author_role` SHALL 为 `human`。

#### Scenario: MVP 消息 author_role 为 human

- **WHEN** MVP 阶段买家或店主成功发送消息
- **THEN** 持久化行的 `author_role` SHALL 为 `human`

#### Scenario: MVP 会话 handler_mode 为 human

- **WHEN** MVP 阶段 lazy create 新会话
- **THEN** `handler_mode` SHALL 为 `human`

### Requirement: Authenticated support API

系统 SHALL 提供 support API。未认证 SHALL 返回 **401**。买家路径当前用户 SHALL 由 JWT `sub` 解析；店主路径 SHALL 使用 `catalog.deps.get_current_shop`。

#### Scenario: 未认证买家 GET 返回 401

- **WHEN** 未认证客户端 `GET /support/shops/{shop_id}/conversation`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 未认证店主 inbox 返回 401

- **WHEN** 未认证客户端 `GET /support/inbox`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Buyer GET conversation

系统 SHALL 提供 `GET /support/shops/{shop_id}/conversation`（需认证）。

#### Scenario: 有会话返回 200

- **WHEN** 认证买家对该 shop 已有会话
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 含 `id`、`shop_id`、`buyer_user_id`、`handler_mode`、`updated_at`、`last_message_preview`

#### Scenario: 无会话返回 404

- **WHEN** 认证买家对该 shop 尚无会话
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: shop 不存在返回 404

- **WHEN** 认证买家请求的 `shop_id` 在 catalog 不存在
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Buyer POST message with lazy create

系统 SHALL 提供 `POST /support/shops/{shop_id}/conversation/messages`（需认证）。请求体 SHALL 为 `{ "body"?: string, "message_refs"?: [{ "ref_type": string, "ref_id": string }] }`。`body` 与 `message_refs` SHALL NOT 同时为空。若无会话 SHALL 在同一事务内创建 `support_conversations` 与首条 `support_messages`；若已有会话 SHALL 追加消息。成功 SHALL 返回 **201** 与消息对象。发消息后 SHALL bump 会话 `updated_at` 并更新 `last_message_preview`。

#### Scenario: 首条消息 lazy create

- **WHEN** 认证买家对 active shop 首次 POST 合法消息
- **THEN** 响应状态码 SHALL 为 201
- **AND** SHALL 创建唯一 `(shop_id, buyer_user_id)` 会话
- **AND** 消息 `sender_role` SHALL 为 `buyer`

#### Scenario: 同 shop 复用会话

- **WHEN** 认证买家对已有会话的 shop 再次 POST
- **THEN** 响应状态码 SHALL 为 201
- **AND** SHALL NOT 创建第二个 `(shop_id, buyer_user_id)` 会话

#### Scenario: 店主自购咨询返回 403

- **WHEN** 认证用户为该 shop 的 `owner_user_id` 并 POST 买家路径消息
- **THEN** 响应状态码 SHALL 为 403
- **AND** SHALL NOT 创建会话或消息

#### Scenario: closed 店买家 POST 返回 422

- **WHEN** 认证买家对 `status=closed` 的 shop POST 消息（无论是否已有会话）
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建新会话（若无会话）

#### Scenario: body 与 refs 皆空返回 422

- **WHEN** 认证买家 POST 且 `body` 为空/缺失且 `message_refs` 为空/缺失
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: body 超长返回 422

- **WHEN** 认证买家 POST 且 `body` 长度超过 2000
- **THEN** 响应状态码 SHALL 为 422

### Requirement: Buyer GET messages

系统 SHALL 提供 `GET /support/shops/{shop_id}/conversation/messages`（需认证）。分页 Query SHALL 符合 **infra-pagination** 契约。消息 SHALL 按 `created_at` **升序**排列。

#### Scenario: 无会话返回 404

- **WHEN** 认证买家对该 shop 尚无会话并 GET messages
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 消息按时间升序

- **WHEN** 认证买家 GET 已有会话的消息列表
- **THEN** `items` SHALL 按 `created_at` 升序
- **AND** 每条 SHALL 含 `sender_role`、`author_role`、`body`、`message_refs`

### Requirement: Shop inbox list

系统 SHALL 提供 `GET /support/inbox`（需认证且 `get_current_shop`）。SHALL 返回**当前店铺**的会话分页列表，按 `updated_at` **降序**。每项 SHALL 含 `last_message_preview`。分页 envelope SHALL 符合 **infra-pagination**。

#### Scenario: inbox 仅含本店会话

- **WHEN** 店主 GET /support/inbox
- **THEN** 返回的每条会话 `shop_id` SHALL 等于当前 shop.id

#### Scenario: 买家发消息后 inbox 排序更新

- **WHEN** 买家向某 shop 发送新消息
- **AND** 店主 GET /support/inbox
- **THEN** 该会话 SHALL 按 `updated_at` 位于较前位置

### Requirement: Shop conversation and messages

系统 SHALL 提供 `GET /support/inbox/{conversation_id}`、`GET /support/inbox/{conversation_id}/messages`、`POST /support/inbox/{conversation_id}/messages`（需 `get_current_shop`）。

#### Scenario: 非本店会话返回 404

- **WHEN** 店主请求的 `conversation_id` 不属于当前 shop
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 店主回复成功

- **WHEN** 店主对属于本店的会话 POST 合法消息
- **THEN** 响应状态码 SHALL 为 201
- **AND** 消息 `sender_role` SHALL 为 `shop`
- **AND** `author_role` SHALL 为 `human`

#### Scenario: closed 店店主仍可回复已有会话

- **WHEN** 当前 shop `status=closed` 且会话已存在
- **AND** 店主 POST 回复
- **THEN** 响应状态码 SHALL 为 201

#### Scenario: 无关用户访问会话返回 404

- **WHEN** 既非会话 buyer 也非该 shop 店主的认证用户 GET 买家或 inbox 会话路径
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Message product refs

系统 SHALL 支持 `message_refs` 中 `ref_type=product`。MVP 收到 `ref_type=order` SHALL 返回 **422**。单条消息 refs 数量 SHALL ≤ 10；重复 `(ref_type, ref_id)` SHALL 去重后计数。校验 SHALL 通过 **catalog.service.validate_product_refs_for_shop**。响应中 refs SHALL 仅含 `{ "ref_type", "ref_id" }`（SHALL NOT enrich 商品详情）。未上架但属于本 shop 的商品 SHALL 允许引用。

#### Scenario: 纯 product ref 无 body 成功

- **WHEN** 认证买家 POST 仅含合法本店 `product` ref、无 body
- **THEN** 响应状态码 SHALL 为 201

#### Scenario: 跨 shop 商品 ref 返回 422

- **WHEN** 认证买家 POST 的 product ref 不属于该会话 shop
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未上架本店商品 ref 成功

- **WHEN** 认证买家 POST 引用本 shop 内 `is_published=false` 的商品
- **THEN** 响应状态码 SHALL 为 201

#### Scenario: order ref 返回 422

- **WHEN** 认证用户 POST 含 `ref_type=order` 的 message_refs
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: refs 超过 10 返回 422

- **WHEN** 认证用户 POST 且去重后 refs 数量大于 10
- **THEN** 响应状态码 SHALL 为 422

### Requirement: Cross-shop conversation isolation

系统 SHALL 按 `(shop_id, buyer_user_id)` 隔离会话。同一买家对不同 shop SHALL 拥有独立会话。

#### Scenario: 两 shop 各一会话

- **WHEN** 同一买家分别向 shop A 与 shop B POST 首条消息
- **THEN** SHALL 创建两条独立会话
- **AND** 各自 `shop_id` SHALL 不同

### Requirement: Cross-domain import discipline

support 域 SHALL NOT import `catalog.models`、`catalog.repository`、`ordering.models` 或 `ordering.repository`。商品与店铺校验 SHALL 仅通过 catalog **service** 与 **schema** 完成。

#### Scenario: support 不直连 catalog ORM

- **WHEN** 审查 `app/support/` 模块 import
- **THEN** SHALL NOT 出现 `from app.catalog.models` 或 `from app.catalog.repository`
