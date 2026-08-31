## Why

Change 3（`ai-support-agent`）把 AI 客服挂在 support 的买家发消息接口上：一次 `POST /support/shops/{shop_id}/conversation/messages` 既写买家消息，又经 Port（support 定义的调用协议）和模块级工厂去调 AI。这是「借入口」的权宜，逼出了注册表税和「一个 HTTP 两套模式」。入口形态决策（ADR-014）已改为前端分流：对话仍走 support，生成走 AI 自己的 HTTP。本刀落地该决策；意图 / RAG / τ（置信度阈值）不重写。

短标签 `[dedicated-entry]`。分支：`refactor/ai-dedicated-entry`。

## What Changes

- **新建 AI HTTP**：`POST /ai/shops/{shop_id}/replies`（需买家 JWT）。无请求 body：从该店该买家会话读库——query 用最近一条非空买家正文；商品过滤用回看的 product refs（见 design）。成功与 LLM/编排失败均为 **200**，并落一条助手消息。
- **落库责任转移**：AI router 调 `support.service` 追加 `sender_role=shop`、`author_role=ai` 的助手行；更新 `last_message_preview`。编排器（今日的 `IntentController`）不 import support。
- **support 变纯对话**：买家 POST **只**落买家消息，**不再**读 `handler_mode` 调 AI。删除 `app/support/ports.py` 与 `register_buyer_turn_handler_factory`。店主 inbox POST 仍不调 AI。
- **`handler_mode` 留下**：会话级「当前窗口是 AI 客服还是人工」（前端开关）。`PATCH /support/shops/{shop_id}/conversation` **保留**。GET 会话仍返回该字段。表列不删、存量不迁。NLU / AI **仍不得**写该字段。
- **装配改名**：`build_buyer_turn_handler` → `build_intent_controller`；由 AI router 调用，不再注册到 support。
- **纯卡片问候**：仅有商品引用、没有非空买家正文时，若仍调用 `/replies`，落问候文案（Git 登记提示词，例如「关于这个商品您有什么想问的吗？」），**不是**转人工文案 `suggest_human`。
- **活文档**：修订 ADR-013（允许 AI router）、ADR-014（收窄：删的是 POST 分派不是 PATCH）、`docs/architecture.md`。

**BREAKING（support 行为）**：`handler_mode=ai` 时买家 POST **不再**自动追加助手消息。前端须在 AI 客服模式下于发消息后再调 `/ai/.../replies`。既有「一次 POST 双写」客户端会停更助手行。

## Capabilities

### New Capabilities

- `ai-http-replies`：AI 域买家回复端点、读库组装一轮输入（正文 + 回看 refs）、问候模板、助手落库与 200 响应契约。

### Modified Capabilities

- `ai-support-agent`：客服入口改为 AI HTTP；知识检索的 `product_id` 按回看后的 refs 计算（不再假设「触发 AI 的那条 HTTP 自带 refs」）；登记问候提示词；装配函数改名。
- `support-conversations`：删除「买家 POST 在 ai 模式下调 Port」；POST 永不写 `author_role=ai`；PATCH / `handler_mode` 语义改为窗口开关而非后端分派。
- `ai-domain-composition`：允许 `app/ai/router.py`；组合根增加 router 装配；退役 support 侧工厂登记。

## Non-goals

- **不做**把会话历史拼进 LLM（全读库）。下一刀评估，再下一刀做简单读库过渡，再下一刀规范；LangGraph 消息管理更后。
- **不做** LangGraph / Checkpointer / 迭代检索 / HITL（人机协作暂停）。
- **不做**把 τ 挪进 RAG handler、重命名 `IntentController` / `NLGateway` / `handle_buyer_turn`（正名另刀）。
- **不做** LLM 计费网关、SSE、drop `handler_mode` 列。
- **不做**前端实现（本仓库无前端）。
- **不改** `retrieve_chunks` 实现、意图注册表内容（仍仅 `knowledge`）、archived OpenSpec 历史正文。

## Impact

- **域**：`ai`（router / schemas / deps）、`support`（去掉 Port 与 POST 内 AI 分支；新增供 AI 调用的追加助手消息）。catalog / ordering / engagement / user / media / infra **无行为变更**（AI 鉴权复用 infra `get_current_user_id`）。
- **API**：新增 `POST /ai/shops/{shop_id}/replies`；support 买家 POST 行为 **BREAKING**（不再双写）；PATCH handler_mode **保留**。
- **依赖方向**：AI → `support.service`（合法叶子）；support **仍不得** import `app.ai`。AST 不新增规则，验证现有检查通过即可。
- **测试**：删/改 `tests/support/test_ai_turn.py` 与「POST 顺带跑 AI」期望；新增 AI 端点 integration；`tests/ai` 目录分层放最后一节。
