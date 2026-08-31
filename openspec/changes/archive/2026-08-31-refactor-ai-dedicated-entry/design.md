## Context

- Change 3 已归档：客服借 `POST /support/shops/{shop_id}/conversation/messages`，`handler_mode=ai` 时经 `BuyerTurnAiHandler` Port 与 `register_buyer_turn_handler_factory` 同步生成助手消息。
- 入口形态决策（ADR-014）推翻「借入口」；会话定稿见 `docs/temp/2026-08-27-ai-dedicated-entry-change-decision.md`，explore 后补：前端先 POST support 落买家消息，再按窗口开关调 AI；PATCH 与 `handler_mode` 字段留下。
- 约束：support **SHALL NOT** import `app.ai`；AI → `support.service` + schema 合法；编排器不 import support；无新表；不改 `retrieve_chunks`。
- 分支：`refactor/ai-dedicated-entry`；短标签 `[dedicated-entry]`。

## Goals / Non-Goals

**Goals:**

- AI 自有 HTTP；support 买家 POST 只写对话。
- 读库组装一轮输入（最近非空买家正文 + 回看 product refs），不把全文历史塞进 LLM。
- 纯卡片问候模板；失败仍 200 + 助手行。
- Port / support 侧工厂退役；`build_intent_controller` 供 AI router 使用。

**Non-Goals:**

见 proposal.md（全读库、LangGraph、τ 挪层、正名 Controller/NLGateway、计费网关、SSE、删列、前端）。

## Decisions

### 1. 前端两步，后端无「一次 POST 双写」

**选择：**

```text
① POST /support/shops/{shop_id}/conversation/messages
     → 校验 + lazy create + 只落买家行（author_role=human）
     → 201 仍为买家 MessageResponse
     → 不读 handler_mode，不调 AI

② 前端若窗口为 AI 客服 → POST /ai/shops/{shop_id}/replies（无 JSON body）
     → 读库组装 (body, product_ref_ids)
     → build_intent_controller().handle_buyer_turn(...) 或纯卡片问候
     → support.service.append_ai_message(...) 
     → 200 + { text, conversation_id, assistant_message_id }

GET /support/.../messages 仍混排。
PATCH handler_mode 仍改窗口开关；NLU / AI 不写该字段。
```

**理由：** 对话时间线已是 support 的事实源；「先甩商品再说话」是两次买家 POST。把生成绑在 ① 上无法表达「卡片不强制调 AI」。

**替代：** AI 端点再传 body/refs → 拒绝（与 ① 重复、易漂移）。AI 端点同时写买家行 → 拒绝（会话 API 已实现）。删 PATCH → 拒绝（刷新后前端不知道该不该打 ②）。

### 2. 读库组装一轮：query 与 refs 分开回看

从新到旧扫该会话消息，**碰到 `author_role=ai` 或 `sender_role=shop` 的店主人工行即停止**（不把上一轮助手之后的货粘过来）。不设条数上限。

| 字段 | 规则 |
|---|---|
| query（`body`） | 停止前最近一条买家消息且 `body` 非空 |
| `product_ref_ids` | 停止前最近一条买家消息且含 product refs；多 ref 仍取该条去重后最后一项（与现知识 handler 一致） |

然后：

- **无会话 / JWT 用户不是该店该会话买家** → 404（归属；店主打此接口通常无「自己当买家」的会话 → 同样 404）。未认证 → 401。
- **有会话、无非空买家 body、但回看到 product refs**（纯卡片）→ **不进 NLU / 不检索**；落问候提示词 `ask_about_product`；200。
- **有会话、无非空 body 且无 refs** → 仍 200，落 `suggest_human` 兜底助手行（前端误调与 LLM 失败同一出口）。
- **有非空 body** → 现有编排器：`handle_buyer_turn(shop_id, body, product_ref_ids)`（`product_ref_ids` 可空 = 整店检索）。

关店 / 商品 refs 合法性 **只**在 ① 的 support POST（既有 `validate_product_refs_for_shop`）。AI **不**重复验店开不开。

**理由：** 规格曾把 refs 绑在「触发 AI 的那条消息」上；两步之后最后一句问话常常没有 refs。回看是最小补丁，不是会话级「当前商品」列（Change 3 已否）。

**替代：** 前端把当前商品复制进每一句 → 拒绝（后端无法约束）。全读库进 LLM → 拒绝（本刀 non-goals）。

### 3. 跨域只走 support.service

AI **SHALL NOT** import support ORM / repository。

公开方法（名称可微调，须在 support 域 service）：

- 列出该买家本店会话消息（schema，供回看）或封装「组装一轮输入」的只读查询。
- `append_ai_message(shop_id, buyer_user_id, text) ->` 含 `id` / `conversation_id` 的 schema：写 `sender_role=shop`、`author_role=ai`，bump preview（截断 200）。

Router：`get_current_user_id`（infra）+ 上列 service。编排器保持纯逻辑、可注入 Fake LLM。

**理由：** 叶子方向 AI → 业务 service（AI 域组合根与消费边界，ADR-013 决策 2）。support 继续零 `app.ai` import。

### 4. 删除 Port 与 support 工厂；装配改名

删除 `BuyerTurnAiHandler`、`register_buyer_turn_handler_factory`、`main.py` 登记、`SupportService` 内 `_run_ai_turn`。

`build_buyer_turn_handler` 改名为 `build_intent_controller`，返回值仍是今日的 `IntentController`（本刀不改类名/方法名）。

**理由：** 工厂是借入口的中间人；前端分流后 support 不再消费 AI。

### 5. HTTP 契约从简

- 无请求 body。成功与失败（LLM / 编排抛错）均为 **200**，且都落助手行（失败用 `suggest_human`）。
- 响应：`text`（助手正文）、`conversation_id`、`assistant_message_id`。不要 `type: ai_answer | fallback_human`（转人工靠 PATCH）。
- 不新建 AI 域表。

### 6. 测试与执行顺序

先红节覆盖：新端点、回看、问候、失败 200、support POST 不再双写、无 Port 符号、AST。再 **先建后拆**（AI router 绿一块，再拆 support）。`tests/ai` 按是否碰 IO 分 `unit/` / `component/` / `integration/` 放 **最后一节**：新文件按新目录；旧文件能搬就搬，不拦拆 Port。

### 7. 文档

apply 修订 ADR-013 决策 1/4/5（允许 router；入口不再借 support）；ADR-014（PATCH 保留；删的是 POST 分派）；architecture.md 客服路径。不改 `openspec/changes/archive/**` 正文（Change 3 design 已有推翻附记则不动）。

## Risks / Trade-offs

- [客户端未改、仍只打 support POST] → 助手不再出现。BREAKING 须在 changelog / architecture 写明。
- [回看粘错商品] → 以「上一轮助手/店主」为墙；不跨墙。
- [AI → support 新依赖] → 可接受的半叶子；独立部署时再换 HTTP。
- [问候与转人工文案混] → 分两个 Git 提示词 id。

## Migration Plan

- 无表迁移。`handler_mode` 列与 PATCH 保持。
- 回滚：恢复 Port 与 POST 内 `_run_ai_turn`（不推荐；前端已按两步则回滚会双写）。

## Open Questions

无。explore 已定：路径、B+回看、问候、200、不做全读库。
