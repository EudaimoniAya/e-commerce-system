## Context

- Change 1–2.1 已归档：PG/pgvector、多源索引、`retrieve_chunks(shop_id, query, top_k, product_id=None)`、组合根 `app/ai/deps.py`、业务域不得 import `app.ai`（ADR-013 + AST）。
- support 已交付店铺会话：`UNIQUE(shop_id, buyer_user_id)`、`message_refs`（仅 product）、`handler_mode` / `author_role` 预留。lazy create 现默认 `human`；写入消息现恒 `author_role=human`；**没有**切换模式的 HTTP。买家 POST 返回 201 买家消息。
- 本刀定稿：`docs/temp/2026-08-24-ai-support-agent-change3-decisions.md`。ADR-013 决策 5 与 ADR-012 Change 3 行仍写「知识 / Tool / 评测集」，apply 时修订为与定稿一致。
- 约束：跨域只走 service + schema；support **SHALL NOT** import `app.ai`；不建 AI HTTP；不改 retrieval 实现；无新表。
- 分支建议：`feature/ai-support-agent`；短标签 `[support-agent]`。

## Goals / Non-Goals

**Goals:**

- 买家在 AI 模式下发消息，同请求内得到知识类 grounded 答复（或 τ / 意图外拒答转人工文案），并落库 `author_role=ai`。
- 意图注册表机制落地，本刀只注册知识类；转人工是兜底分支不是注册意图。
- 前端可 PATCH 切人工；人工模式不进 NLU。
- 提示词 Git 登记；CI Mock LLM / Mock Embedder；dev 可接 DeepSeek 与真 Embedder。

**Non-Goals:**

见 proposal.md Non-goals（查询类 Tool、空意图占位、AI router、RAGAS/τ 标定、检索深化、Outbox、前端、订单 ref）。

## Decisions

### 1. 消息入口复用 support HTTP，不建 AI router

**选择**：继续 `POST /support/shops/{shop_id}/conversation/messages` + `MessageCreate`，同步 JSON。不新增 `app/ai/router.py`、不新增 `/ai/*`。

**同请求语义**：

```text
买家 POST
  → support 校验 + 落买家消息（sender_role=buyer, author_role=human）
  → 若 handler_mode=ai 且 Port 已注入：调用 Port，得到助手正文
  → 落助手消息（sender_role=shop, author_role=ai）
  → 201 响应体仍是买家那条 MessageResponse
  → last_message_preview 更新为助手正文截断（人工模式则仍为买家正文）
```

客户端用既有 `GET .../messages` 看到两条。店主 inbox POST **不**调 Port。

**理由**：定稿明确不建 AI HTTP；support 已是会话唯一事实源。拆 AI 路由会让前端（未来）对同一会话打两个入口，和「一买家一店一会话」冲突。

**替代**：`POST /ai/shops/{id}/messages` → 拒绝（定稿）。SSE → 拒绝。201 改为返回助手消息或 turn DTO → 拒绝，打破现有 MessageResponse 契约。

### 2. support 不 import ai：Port 返回正文，main.py 注入工厂

**选择**：在 `app/support/ports.py` 定义：

```python
class BuyerTurnAiHandler(Protocol):
    async def handle_buyer_turn(
        self, *, shop_id: uuid.UUID, body: str | None, product_ref_ids: list[str]
    ) -> str
```

`SupportService` 可选依赖该 Port。`app/support/deps.py` 经模块级 `register_buyer_turn_handler_factory` 取工厂（**不** import `app.ai`）。`app/main.py`（组合根，AST 豁免）在 `create_app` 中：

```text
register_buyer_turn_handler_factory(build_buyer_turn_handler)  # 来自 app.ai.deps
```

测试可注入可编程 Mock Port，不走 LLM。

Port **只返回字符串**；落库、preview、事务仍在 support.service。避免 support.service ↔ agent 循环调用。

买家消息先 commit（或 flush 可见）再调 Port：LLM 慢不长时间锁行；Port 失败时买家消息已在，助手改为兜底文案（`suggest_human` 模板），**SHALL NOT** 用 5xx 吞掉买家 POST。

**理由**：ADR-013 业务域不得 import ai；`main.py` 已是合法组合根。Handler 自己调 `support.service.append_*` 会造成循环与双事务。

**替代**：support.deps 直接 `from app.ai.deps import ...` → 拒绝，AST 红。事件/后台任务 → 拒绝，定稿要同步 JSON。

### 3. 会话默认 AI；转人工只走 PATCH；NLU 不改模式

**选择**：

- lazy create：`handler_mode="ai"`（ORM default / server_default 同步改）。
- 新增 `PATCH /support/shops/{shop_id}/conversation`，body `{ "handler_mode": "ai" | "human" }`，仅该会话买家。成功 200 + `ConversationResponse`。非法值 422；无会话 404。
- `handler_mode=human` 时买家 POST 行为与今日相同（不调 Port）。
- NLU / handler **SHALL NOT** 写 `handler_mode`。过载只返回登记的转人工文案（仍以 `author_role=ai` 落库，因为撰写者是系统；模式仍是 ai，直到用户 PATCH）。

既有库内 `human` 行不迁移。

**理由**：定稿「会话默认 AI」「转人工 = 前端 → support」。助手文案建议转人工若同时改模式，用户无法忽略建议。

**替代**：店主 inbox 也能 PATCH → 本刀不做（定稿是用户/前端；店主接管可下一刀）。NLU 执行转人工 → 拒绝（ADR-013）。

### 4. 意图：注册表机制本刀建，只注册知识类；转人工是分支

**选择**：

```text
IntentRegistry（本 agent 一份）
  └── knowledge   handler: retrieve_chunks + rag_answer + LLM

兜底分支（不是注册表项）
  └── handoff     渲染 suggest_human，不调 retrieve、不调 LLM 生成
```

NL 网关输出 `{intent, confidence}`。进入知识 handler 当且仅当 `intent == knowledge` **且** `confidence >= τ`。否则走 handoff。禁止把未注册意图映射到 knowledge。

NLU 提示词须写明：价格 / 库存 / 订单 / 投诉 / 闲聊 / 不明 → 不得输出 knowledge。

下一个 change 再 `registry.register(price_stock, handler)`，不在本刀预留空槽。

**理由**：8/18 分水岭（RAG 是一个意图）+ 定稿「逐个 change 注册」+ 砍投机门面（零调用方不预建）。

**替代**：一次注册 11 意图空 handler → 拒绝。规则分类器无 LLM → 拒绝，无法用同一套 Mock 测「集外拒识」提示词合同。

### 5. 知识 handler：复用 retrieve_chunks；product_id 取本条消息 refs

**选择**：调用 `app.ai.rag.retrieval.service.retrieve_chunks`（ai 域内）。过滤键：

| 本条消息 product refs（已校验、去重、顺序保留） | `product_id` 参数 |
|---|---|
| 0 | `None`（整店） |
| 1 | 该 id |
| ≥2 | **最后一个** |

`body` 为空的纯 ref 消息：query 用固定占位（如商品咨询）或跳过 NLU 直接 knowledge？**选择**：纯 ref 仍进 NL 网关，query 为空串时 retrieval 现契约返回 `[]` → 走空检索拒答（与 τ 未达相同文案）。避免为「只甩卡片」另开意图。

检索空列表 → 不调用生成 LLM，handoff/拒答模板。

生成只依据 chunk 文本；prompt 禁止编造。

**跨域**：不调 catalog.service 取价；校验 refs 仍是 support 既有 `validate_product_refs_for_shop`。

**替代**：会话级「当前商品」列 → 拒绝，表无该列。多个 ref 整店检索 → 拒绝，串货。多个 ref 循环 retrieve 合并 → 本刀不做。

### 6. τ 最小版：一个 [0,1] 配置阈值

**选择**：Settings `TAU_THRESHOLD`（float，默认 **0.3**，手工低值）。语义：置信度 / 质量分 **低于** τ → 拒答走 handoff 文案。

本刀分数源只有 NLU `confidence`。空检索 **视为未达 τ**（不另引入余弦距离阈值：`retrieve_chunks` 的 score 是距离，越小越好，和 [0,1] 置信度不同标，避免本刀标定）。

不做生成后再打分（那是 RAGAS）。

纯函数 `passed_tau(score: float, threshold: float) -> bool`，单测边界。

**替代**：用 chunk 余弦距离当 τ → 拒绝，标尺相反且需标定。本刀上 RAGAS → 拒绝。

### 7. 提示词 Git 登记

**选择**：`app/ai/prompts/*.yaml`，字段 `id`、`version`、`template`。加载器按 id 读文件、填充变量，返回 `(text, id, version)`。LLM 调用日志带 `prompt_id` + `version`。

本刀三份：`nlu_route`、`rag_answer`、`suggest_human`（后者可不调 LLM）。

组合根 `build_prompt_loader()`。禁止在 classifier.py 堆长 f-string。

**替代**：LangSmith Hub / DB 表 → 拒绝（定稿）。抄 jd-service 把 NLU 写进 Python → 拒绝。

### 8. LLM：协议 + Mock + DeepSeek；装配在 ai.deps

**选择**：与 Embedder 同构，但放在 **ai 域**（仅 agent 使用，infra 不膨胀）：

```text
LLMClient.generate(messages) -> str
├── MockLLMClient     CI / 单测注入（可编程 JSON / 正文）
└── DeepSeekClient    OpenAI 兼容 HTTP；dev 手验
```

Settings：`LLM_PROVIDER`（`mock` | `deepseek`）、`LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`（deepseek 默认 `https://api.deepseek.com`）。CI 与 pytest 默认 `mock`。`app/ai/deps.py` 的 `build_llm_client()` 按环境构造。

pytest **SHALL NOT** 打真实 DeepSeek。真厂商 IO 不进 CI。

**替代**：LLM 放 infra 与 Embedder 并列 → 可后移，本刀无第二调用方。LangChain ChatOpenAI 作为唯一实现、无 Protocol → 拒绝，CI 难测调度。

### 9. Embedder：本刀落地 zhipu / dashscope 真 HTTP

**选择**：实现 `ZhipuEmbedder.embed_texts` / `DashscopeEmbedder.embed_texts`（httpx，超时与错误 fail-fast）。维度仍须等于 `EMBEDDING_DIMENSION`。CI `EMBEDDING_PROVIDER=mock` 不变。单测 mock HTTP，断言路由 URL / 返回向量长度。

不新增 DeepSeek Embedder（配置注释已写清：对话模型与 embedding 厂商可分离）。

**替代**：只做客服、Embedder 仍骨架 → 拒绝（定稿本刀即接，为了验维度与厂商路由）。

### 10. 文档修订落在本 change 的 apply，不改 archive

**选择**：apply 修订活文档：ADR-013 决策 5（首批仅知识 + 转人工提示）、ADR-012 Change 3 行（评测集/τ 标定移出，τ 仅最小版）、`architecture.md` 客服路径。archived change2 的 Decision 12/14 **不改历史文件**；本 design 覆盖「事实类 Tool 延后」。

## Risks / Trade-offs

- [同步 LLM 拉长买家 POST] → 超时兜底文案仍 201；以后可 SSE，本刀不做。
- [默认 AI 让既有 support 测试大面积红] → 红节一次性改期望；人工路径用 PATCH 或注入 Null Port 覆盖。
- [仅一个意图时 NLU 易把「多少钱」判成 knowledge] → 提示词合同 + τ + 集外测试（Mock 固定输出 unknown）；真模型质量归离线评测。
- [Port 注入失败 / 忘记 register] → `handler_mode=ai` 但工厂为空时视为 handoff 文案，不 500。
- [真 Embedder 与 Mock 向量空间不同] → CI 仍 Mock；dev 换厂商须 reindex（已有 CLI）。

## Migration Plan

- 无新表。改 `handler_mode` 的 ORM / server_default；已有会话保持原值。
- 配置：`.env.example` 增加 LLM_*、TAU_THRESHOLD；CI 不配真 key。
- 回滚：去掉注入即回到「不调 Port」；默认改回 human 需再发版（本刀不提供开关双默认）。

## Open Questions

无。定稿已覆盖入口、默认模式、refs 过滤、τ 最小版、LLM/Embedder、意图注册策略。

---

## 演进记录（2026-08-25，合并后追加）

> 本 change 已合并归档。以下记录**本 change 上线后对其设计决策的推翻**，正文保持归档快照原样，不追溯修改。

**决策 1-3 被 [ADR-014](../../../docs/decision/ADR-014-AI入口形态-前端分流.md) 推翻（AI 入口形态：前端分流）**：

- 决策 1（借 support 入口、不建 AI router）→ 推翻：AI 域开自己的 `app/ai/router.py`，前端分别调用 AI 端点 / support 端点。复盘根因：借入口是**权宜**（非约束），从它推出的注册表整条链是伪必然——详见踩坑记录 `docs/troubleshooting/ai域-入口形态-借support到前端分流.md`（"权宜伪装成约束"）。
- 决策 2（Port + `register_buyer_turn_handler_factory`）→ 推翻：前端分流后 support 不再消费 AI 能力，注册表与 `BuyerTurnAiHandler` Port 退役；落库责任转移到 AI router（AI → `support.service`，合法叶子方向）；`controller` 保持纯净（不 import support）。
- 决策 3（`handler_mode` 会话状态机 + PATCH 切人工）→ 推翻：`handler_mode` 是实现状态机（非领域状态机），前端分流后模式由"端点选择"表达，后端无模式状态；驱动逻辑与 PATCH 删除，字段留作历史数据。转人工信号改由 AI 端点结构化响应（`{type: ai_answer | fallback_human}`）传给前端。
- 保留不变：意图注册表机制（消费者变为 AI router 内部）、逐个 change 注册纪律、RAG 是库、叶子依赖方向、`author_role` 审计。

落地 change：`refactor/ai-frontend-split`（含 AI 域测试规范 + 架构规范设立）。
