## Why

Change 1–2.1 已交付 pgvector、多源索引与 `retrieve_chunks`（含可选 `product_id`），买家仍不能在店铺会话里得到一句 grounded 的 AI 答复。v2.0.0 的可演示切面是「智能客服」而不是「又一个检索 HTTP」：本刀把 RAG 收成**知识类意图的底层能力**，经 NL 网关接到已有 support 消息入口。

决策定稿见 `docs/temp/2026-08-24-ai-support-agent-change3-decisions.md`（用户逐条裁决）。短标签 `[support-agent]`。

## What Changes

- **NL 网关 + 场景隔离意图注册表 + IntentController**：每 agent 一份注册表；本刀只注册**知识类**意图。无真实 handler 的意图不占位。
- **知识类 handler**：消费已有 `retrieve_chunks`（不改检索实现）。`message_refs` 决定过滤：0 个 ref → 仅 `shop_id`；1 个 → 该 `product_id`；多个 → 本条消息**最后一个** product ref。
- **会话默认 AI**：lazy create 的 `handler_mode` 从 `human` 改为 `ai`。support 新增买家 `PATCH` 供前端切 `human` / `ai`。NLU **不**改会话模式；意图过载只出转人工**文案**。
- **入口复用 support HTTP**：不建 `app/ai/router.py`。买家 `POST /support/shops/{shop_id}/conversation/messages` 仍用 `MessageCreate`、同步 JSON；`handler_mode=ai` 时同请求内生成并落库助手消息（`sender_role=shop`、`author_role=ai`）。POST 响应仍是买家那条（201），助手消息经随后 GET messages 可见。
- **support 不 import ai**：AI 实现 support 侧 Port，由 `main.py` 注册工厂注入；助手正文由 Port 返回，support.service 负责写入。
- **提示词 Git 登记**：`id` + `version` + 加载器；调用打日志。不进 DB / Hub。
- **τ 最小版**：单一 `[0,1]` 阈值 + 拒答/转人工兜底。阈值手工低值；兼任 NLU 置信度闸。空检索视为未达 τ。不做标定、不做 RAGAS。
- **LLM**：协议 + `MockLLMClient`（CI）+ `DeepSeekClient`（dev / 离线评测）。测试不测模型文案，测调度 / 路由 / 落库。
- **Embedder 接真厂商**：落地 `ZhipuEmbedder` / `DashscopeEmbedder` 的真实 HTTP；CI 仍 `EMBEDDING_PROVIDER=mock`。
- **文档**：修订 ADR-012 Change 3 行、ADR-013 决策 5、`architecture.md`（与定稿对齐；事实类 Tool 与评测集移出本刀）。

**BREAKING（support 行为）**：新会话默认 `handler_mode=ai`；买家 POST 在 AI 模式下会同步多写一条 `author_role=ai` 消息（响应 envelope 不变）。既有「默认 human / 仅 human 作者」场景作废。

## Capabilities

### New Capabilities

- `ai-support-agent`：NL 网关、意图注册表、IntentController、知识类 handler、提示词登记、LLM 协议（Mock / DeepSeek）、τ 最小门禁、转人工兜底分支；经 Port 被 support 调用。

### Modified Capabilities

- `support-conversations`：默认 `handler_mode=ai`；买家 PATCH 切换模式；`handler_mode=ai` 时买家 POST 触发 AI Port 并写入 `author_role=ai`；人工模式不进 NLU；support 模块仍不得 import `app.ai`。
- `ai-domain-composition`：组合根增装配 LLM / PromptLoader / Agent（及 Port 实现）；**仍不**新增 AI HTTP router；业务域不得 import ai 的禁令不变。
- `infra-ai-pgvector`：`zhipu` / `dashscope` Embedder 从骨架改为真实 HTTP；CI 继续 mock；单测用 httpx mock 验维度与厂商路由。

## Non-goals

- **不做查询类 Tool**（价格 / 库存 / 订单）：事实类意图不在本刀注册表，随下一个 change 注册。
- **不做无真实 handler 的意图注册**（禁止空 handler / 空占位）。
- **不做意图集外输入的静默应答**：未识别或置信度低于 τ → 转人工兜底；禁止把「多少钱」硬塞进知识类再 retrieve。
- **不做 τ 标定**（多阈值 / 历史统计 / 自动标定 → change 4–6）。
- **不建 AI HTTP 路由**；不做 SSE / 流式。
- **不重做读侧**（不改 `retrieve_chunks` 实现）。
- **不做黄金集 / RAGAS 分层归因**。
- **不做检索深化**（rerank、混合检索、HNSW、新 `source_kind`、GraphRAG、LC Retriever）。
- **不做 Outbox / 队列**（同步仍为 CLI reindex）。
- **不做前端**。
- **不做订单查询**（support 订单 ref 仍 422）。

## Impact

- **域**：`ai`（主）、`support`（会话默认、PATCH、Port 注入与 ai 消息写入）、`infra`（Embedder 真 HTTP + LLM/τ 配置项）。catalog / ordering / engagement / user / media **无行为变更**（知识检索仍走已有 retrieval；不新增 Tool）。
- **代码**：`app/ai/`（agent、nlu、prompts、llm、deps 装配）、`app/support/`（service / deps / ports / router PATCH）、`app/main.py`（注册工厂）、`app/infra/embedder.py`、`app/infra/config.py`、对应 tests、ADR-012/013、`architecture.md`。
- **API**：复用买家 POST/GET messages；**新增** `PATCH /support/shops/{shop_id}/conversation`（`handler_mode`）。无 `/ai/*`。
- **依赖**：DeepSeek 走 OpenAI 兼容 HTTP（dev）；CI 不发外网 LLM/Embedding。
- **测试**：CI 全 Mock（调度 / 路由 / 落库 / τ 边界 / PATCH）；真 DeepSeek / 真 Embedder 不进 pytest。既有 support 默认 human 用例按新默认与 AI 注入点更新。
