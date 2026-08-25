# support-conversations

## MODIFIED Requirements

### Requirement: Message identity and handler_mode defaults

系统 SHALL 在每条消息上区分 `sender_role`（对话侧）与 `author_role`（撰写者）。会话 SHALL 含 `handler_mode` 表示当前 AI 是否参与。lazy create 新会话时 `handler_mode` SHALL 为 `ai`。买家与店主经既有 POST 写入的人工消息 `author_role` SHALL 为 `human`。由 AI Port 返回并落库的助手消息 `author_role` SHALL 为 `ai` 且 `sender_role` SHALL 为 `shop`。

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

## ADDED Requirements

### Requirement: Buyer PATCH handler_mode

系统 SHALL 提供 `PATCH /support/shops/{shop_id}/conversation`（需认证）。请求体 SHALL 为 `{ "handler_mode": "ai" | "human" }`。仅会话买家可改本店该会话模式。成功 SHALL 返回 **200** 与 `ConversationResponse`。无会话 SHALL **404**。非法枚举 SHALL **422**。未认证 SHALL **401**。NLU / AI Port SHALL NOT 调用此接口或直接写 `handler_mode`。

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

### Requirement: AI port on buyer POST when mode is ai

当会话 `handler_mode=ai` 且已注入 `BuyerTurnAiHandler` 时，买家 POST 在落库买家消息之后 SHALL 同步调用 Port，并将返回正文落库为助手消息（`sender_role=shop`、`author_role=ai`）。买家 POST 的 HTTP 响应 SHALL 仍为 **201** 且 body SHALL 为买家那条消息。`last_message_preview` SHALL 更新为助手正文截断（上限仍 200）。`handler_mode=human` 时 SHALL NOT 调用 Port、SHALL NOT 写 `author_role=ai` 行。店主 inbox POST SHALL NOT 调用 Port。support 域模块 SHALL NOT import `app.ai`；Port 由 `main.py` 注册的工厂注入。Port 抛错时买家消息 SHALL 仍 201，助手 SHALL 写入兜底文案而非让请求 5xx。未注入工厂且模式为 ai 时 SHALL 写入同一兜底文案，SHALL NOT 500。

#### Scenario: AI 模式双写消息

- **WHEN** 会话 `handler_mode=ai` 且 Port 返回非空正文，认证买家 POST 合法消息
- **THEN** 响应状态码 SHALL 为 201 且响应 `author_role` 为 `human`
- **AND** GET messages SHALL 含随后一条 `author_role=ai` 且 `sender_role=shop` 的消息

#### Scenario: 人工模式不写 AI 消息

- **WHEN** 会话 `handler_mode=human` 且认证买家 POST 合法消息
- **THEN** 响应 201
- **AND** GET messages SHALL NOT 含本轮新增的 `author_role=ai` 消息

#### Scenario: 店主回复不触发 Port

- **WHEN** 会话 `handler_mode=ai` 且店主 inbox POST 合法消息
- **THEN** 响应 201
- **AND** SHALL NOT 因该 POST 新增第二条 `author_role=ai` 消息

#### Scenario: support 不 import app.ai

- **WHEN** 检查 `app/support/` 模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块
