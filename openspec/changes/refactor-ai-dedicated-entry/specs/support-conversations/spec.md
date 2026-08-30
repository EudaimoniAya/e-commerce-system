# support-conversations

## ADDED Requirements

### Requirement: Buyer POST never invokes AI

买家 `POST /support/shops/{shop_id}/conversation/messages` SHALL 只校验并落买家消息（`sender_role=buyer`、`author_role=human`）。SHALL NOT 根据 `handler_mode` 调用 AI，SHALL NOT 在该 POST 的同一请求内写入 `author_role=ai` 行。店主 inbox POST SHALL NOT 调用 AI。support 域模块 SHALL NOT import `app.ai` 任何模块。SHALL NOT 保留 `BuyerTurnAiHandler` 或 `register_buyer_turn_handler_factory`。

#### Scenario: ai 窗口下买家 POST 仍只有买家行

- **WHEN** 会话 `handler_mode=ai` 且认证买家 POST 合法消息（不随后调用 AI 端点）
- **THEN** 响应状态码 SHALL 为 201 且响应 `author_role` 为 `human`
- **AND** GET messages SHALL NOT 因该 POST 新增 `author_role=ai` 消息

#### Scenario: 人工窗口买家 POST 不写 AI 行

- **WHEN** 会话 `handler_mode=human` 且认证买家 POST 合法消息
- **THEN** 响应 201
- **AND** GET messages SHALL NOT 含本轮新增的 `author_role=ai` 消息

#### Scenario: support 不 import app.ai

- **WHEN** 检查 `app/support/` 模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块

#### Scenario: 无 Port 与工厂符号

- **WHEN** 检查 `app/support/` 与 `app/main.py`
- **THEN** SHALL NOT 存在 `BuyerTurnAiHandler` 类型或 `register_buyer_turn_handler_factory`

### Requirement: Append AI message via support service

support 域 SHALL 提供供 AI 调用的 service 方法：按 `shop_id` 与买家用户 id 追加助手消息（`sender_role=shop`、`author_role=ai`），并更新 `last_message_preview`（正文截断上限仍 200）。该方法 SHALL 返回含消息 `id` 与 `conversation_id` 的 schema。无会话 SHALL 失败（由 AI HTTP 映射为 404）。

#### Scenario: 追加助手后 preview 为助手截断

- **WHEN** AI 路径成功调用追加助手且正文非空
- **THEN** 会话 `last_message_preview` SHALL 为该正文截断
- **AND** GET messages SHALL 含该 `author_role=ai` 行

## MODIFIED Requirements

### Requirement: Message identity and handler_mode defaults

系统 SHALL 在每条消息上区分 `sender_role`（对话侧）与 `author_role`（撰写者）。会话 SHALL 含 `handler_mode` 表示当前窗口是 AI 客服还是人工（前端开关），**不是**买家 POST 是否调用 AI 的后端分派。lazy create 新会话时 `handler_mode` SHALL 为 `ai`。买家与店主经 support POST 写入的人工消息 `author_role` SHALL 为 `human`。经 AI HTTP 落库的助手消息 `author_role` SHALL 为 `ai` 且 `sender_role` SHALL 为 `shop`。

#### Scenario: 买家 POST 的买家行 author_role 为 human

- **WHEN** 认证买家成功 POST 消息
- **THEN** 该条响应所代表的买家消息 `author_role` SHALL 为 `human`
- **AND** `sender_role` SHALL 为 `buyer`

#### Scenario: 新会话 handler_mode 为 ai

- **WHEN** 认证买家对尚无会话的 shop 首次 POST 合法消息
- **THEN** 创建的会话 `handler_mode` SHALL 为 `ai`

#### Scenario: 店主回复 author_role 仍为 human

- **WHEN** 店主对属于本店的会话 POST 合法消息
- **THEN** 该条 `author_role` SHALL 为 `human`
- **AND** `sender_role` SHALL 为 `shop`

### Requirement: Buyer PATCH handler_mode

系统 SHALL 提供 `PATCH /support/shops/{shop_id}/conversation`（需认证）。请求体 SHALL 为 `{ "handler_mode": "ai" | "human" }`。仅会话买家可改本店该会话窗口开关。成功 SHALL 返回 **200** 与 `ConversationResponse`（仍含 `handler_mode`）。无会话 SHALL **404**。非法枚举 SHALL **422**。未认证 SHALL **401**。NLU 与 AI 编排 SHALL NOT 调用此接口或直接写 `handler_mode`。

#### Scenario: 买家切到 human

- **WHEN** 认证买家对已有会话 PATCH `handler_mode=human`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 会话 `handler_mode` SHALL 为 `human`

#### Scenario: 无会话 PATCH 返回 404

- **WHEN** 认证买家对尚无会话的 shop PATCH handler_mode
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 非法 handler_mode 返回 422

- **WHEN** 认证买家 PATCH 的 `handler_mode` 不是 `ai` 或 `human`
- **THEN** 响应状态码 SHALL 为 422

## REMOVED Requirements

### Requirement: AI port on buyer POST when mode is ai

**Reason**：入口改为前端分流；买家 POST 不再同步调用 AI。助手消息由 `POST /ai/shops/{shop_id}/replies` 经 support service 追加。

**Migration**：客户端在 AI 窗口下于买家 POST 之后调用 AI replies 端点。删除 `app/support/ports.py` 与工厂登记。
