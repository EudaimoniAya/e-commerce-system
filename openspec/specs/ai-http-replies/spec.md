# ai-http-replies

## Purpose

AI 专用 HTTP 入口：买家经 `POST /ai/shops/{shop_id}/replies` 触发 AI 回复。读库回看组装 turn（query 与 product refs），纯卡片路径不经 NLU 返回 Git 登记问候，生成失败仍 200 落转人工兜底行。

## Requirements

### Requirement: Buyer AI reply endpoint

系统 SHALL 提供 `POST /ai/shops/{shop_id}/replies`（需认证）。请求 SHALL NOT 要求 JSON body。买家身份 SHALL 由 infra `get_current_user_id`（JWT `sub`）解析。成功与生成失败时 HTTP 状态码 SHALL 均为 **200**。响应体 SHALL 含 `text`（助手正文）、`conversation_id`、`assistant_message_id`。SHALL NOT 使用 `type: ai_answer | fallback_human` 判别器。未认证 SHALL **401**。该店该买家无会话、或当前用户不是该会话买家 SHALL **404**。

#### Scenario: 未认证返回 401

- **WHEN** 未认证客户端 POST `/ai/shops/{shop_id}/replies`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 无会话返回 404

- **WHEN** 认证买家对该 shop 尚无 support 会话并 POST replies
- **THEN** 响应状态码 SHALL 为 404
- **AND** SHALL NOT 创建会话或消息

#### Scenario: 有问句时 200 并落助手行

- **WHEN** 认证买家对该 shop 已有会话，最近买家连发含非空 body，并 POST replies
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应 SHALL 含非空 `text`、`conversation_id`、`assistant_message_id`
- **AND** GET support messages SHALL 含对应 `author_role=ai` 且 `sender_role=shop` 的消息

### Requirement: Assemble turn from conversation messages

系统 SHALL 从该会话消息由新到旧扫描，在遇到 `author_role=ai` 或店主人工消息（`sender_role=shop` 且 `author_role=human`）时停止。SHALL NOT 设回看条数上限。query SHALL 为停止前最近一条买家消息的非空 `body`。product refs SHALL 为停止前最近一条含 product `message_refs` 的买家消息；多个 product ref 时 `product_id` SHALL 为该条去重后最后一项。SHALL NOT 把会话全文拼进 LLM。组装与落库 SHALL 经 support **service** + schema，AI 模块 SHALL NOT import support ORM 或 repository。

#### Scenario: 先卡片后问句则按卡片过滤

- **WHEN** 买家先 POST 仅含本店 product ref 的消息，再 POST 非空 body 且无 refs，然后 POST replies
- **THEN** 知识检索的 query SHALL 为后一句 body
- **AND** `retrieve_chunks` 的 `product_id` SHALL 等于卡片那条的 product `ref_id`（仅一个 ref 时）

#### Scenario: 助手消息切断回看

- **WHEN** 更早买家消息带商品 A 的 ref，其后已有 `author_role=ai` 行，再后买家只发无 refs 的问句
- **THEN** 本轮 `product_id` SHALL NOT 使用商品 A（回看不得越过该助手行）

### Requirement: Card-only greeting without NLU

当停止前回看到 product refs 且没有任何非空买家 body 时，系统 SHALL 返回并落库问候文案（Git 登记提示词，id 如 `ask_about_product`），SHALL NOT 调用 NL 网关，SHALL NOT 调用 `retrieve_chunks`，SHALL NOT 使用 `suggest_human` 转人工文案。HTTP SHALL 为 200。

#### Scenario: 纯卡片调 replies 得到问候

- **WHEN** 会话在上一轮助手墙之内仅有买家纯 product ref 消息（无非空 body），认证买家 POST replies
- **THEN** 响应 200
- **AND** `text` SHALL 为问候模板（非 `suggest_human` 正文）
- **AND** SHALL 落一条 `author_role=ai` 消息

### Requirement: Generation failure still 200 with fallback row

当存在非空买家 body 且编排器或 LLM 抛错时，系统 SHALL 仍返回 **200**，SHALL 落一条助手消息，正文 SHALL 为已登记的 `suggest_human` 文案。SHALL NOT 以 5xx 结束该请求。

#### Scenario: LLM 抛错仍 200

- **WHEN** 认证买家 POST replies 且生成路径抛错
- **THEN** 响应状态码 SHALL 为 200
- **AND** GET messages SHALL 含本轮 `author_role=ai` 行且正文为转人工模板
