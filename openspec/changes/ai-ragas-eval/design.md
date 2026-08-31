## Context

- 知识类闭环已归档：`retrieve_chunks` + `KnowledgeHandler`（`rag_answer`）+ `POST /ai/shops/{shop_id}/replies`。τ 手工 0.3；无离线质量测量。
- ADR-012 评测路径（黄金测试集 → retriever/generator 分层）从 Change 3 移出，本刀落地第一段。
- 约束：不改客服运行时；评测绑叶子不绑 HTTP / 回看；`ragas` 不进生产依赖；CI 不跑裁判。
- 探索拍板见会话：指标 Faithfulness + Context recall；人手 20–40 条；Eval 店冻快照；裁判另一家 GPT。
- 分支：`feature/ai-ragas-eval`；短标签 `[ragas-eval]`。

## Goals / Non-Goals

**Goals:**

- 可复跑的离线跑道：黄金测试集 + Eval 店快照 + adapter → RAGAS 两指标。
- CI 只守接线（解析、填 Sample、主依赖无 ragas）；真打分离线。
- `retrieve_chunks` 仍是检索唯一入口；生成复用 `rag_answer` 登记提示词 + 现有 `LLMClient`。

**Non-Goals:**

见 proposal.md（运行时回看、τ 标定、多轮、precision/relevancy、trace、前端、LangGraph）。

## Decisions

### 1. 评测绑叶子，不绑 `/replies`

**选择：**

```text
黄金测试集.question + shop_id + product_id
        → retrieve_chunks(shop_id, query, product_id)
        → retrieved_contexts = chunk.content_text
        → retrieved_context_ids = "{document_id}:{chunk_index}"
        → generate：rag_answer 模板 + DeepSeek（LLMClient）
        → SingleTurnSample → Faithfulness + Context recall
```

`product_id` 写在样本上（可空=整店），**不**调用 `assemble_turn`。纯卡片问候不进本集。

**理由：** HTTP/NLU/τ/回看是接线测已覆盖的；RAGAS 要的是检索与生成质量。绑 `/replies` 会逼运行时加 trace。

**替代：** 打 `/replies` 黑盒 → 拒绝。先做 agent trace → 拒绝（编排税）。

### 2. 黄金测试集形状与 Eval 店快照

**选择：** 仓库 `evals/golden/<snapshot_id>/`

- `manifest.yaml`：snapshot_id、embedder 提供方/维度、Eval 店标识、reindex 说明。
- `samples.jsonl`：每行 `id`, `question`, `shop_id`, `product_id`（null 允许）, `reference`（参考答案，Faithfulness 可不依赖，Context recall 需要应召回信息）, `reference_context_ids`（`document_id:chunk_index` 列表）。
- Eval 店：git 剧本（商品 name/description，可选 media 文本）+ 种子脚本经 **catalog.service / media.service** 写入 MySQL，再 `reindex_shop` 写入 PG。禁止评测代码 import catalog/media ORM。
- 快照与 chunk id 对齐；改切块/embedder 后升 `snapshot_id` 并重对 `reference_context_ids`。

条数 20–40，覆盖：有 `product_id` 的商品问、整店泛问、易幻觉（资料没有的事实）。

**理由：** 管线与测试集必须同版本，否则 recall 假摔。pytest `clean_ai_chunks` 店不能当基线。

**替代：** 公开 Amnesty QA 当产品基线 → 拒绝（无店/品/ACL）。金标存 chunk 原文模糊匹配 → 拒绝（第一刀选 id 对齐）。现场每次 reindex 不冻 → 拒绝。

### 3. 生成 adapter 复用提示词，不走 NLU

**选择：** eval generate 加载 `rag_answer`，用 chunks 的 `content_text` 填 `{chunks}`、问句填 `{body}`，调 `build_llm_client().generate`。空检索：不调生成，`response` 为已登记 `suggest_human` 正文（与 handler 空检索一致）。**不**调用 `IntentController.handle_buyer_turn`。

**理由：** 评的是 RAG 叶子，不是意图路由。空检索仍要有 `response` 才能组 Sample。

**替代：** 抽 `KnowledgeHandler` 生成段为共享函数 → 本刀可不抽，允许 eval 与 handler 各填模板（须同一 prompt id）；若 apply 时两处漂移再抽，行为不变。

### 4. 裁判与生成密钥分离

**选择：** 生成继续 `LLM_PROVIDER` / `LLM_*`（离线评测用 deepseek）。裁判：独立环境变量（如 `RAGAS_JUDGE_API_KEY` / `RAGAS_JUDGE_BASE_URL` / `RAGAS_JUDGE_MODEL`），OpenAI 兼容 GPT。写入 `.env.example` 注释：仅离线、不进 CI。

**理由：** 拍板「另一家 GPT」避免生成模型自评过松。中文 chunk + 英文裁判有偏差，第一刀接受，报告里注明。

**替代：** 与 DeepSeek 同一只 → 拒绝（已拍板）。检索用 id 命中、生成才上裁判 → 可作为 recall 的非 LLM 校验 **附加**（`reference_context_ids` 是否 ⊆ 检索 id），不替代 RAGAS Context recall 的 LLM 路径；CI 可只断言 id 集合的确定性命中（见 Decision 6）。

### 5. `ragas` 可选组，检索实现仍禁 LangChain Retriever

**选择：** `pyproject.toml` `[dependency-groups] eval`（或等价 extra）含 `ragas`；生产 `dependencies` 不含。`app/ai/rag/retrieval/` **仍不得** import langchain 作检索。eval runner 允许为 RAGAS 适配 import ragas（仅 `app/ai/evals/` 或 `evals/` 脚本）。

Runner 入口：`python -m app.ai.evals.runner`（或 `evals/run.py` 调组装函数），读 `evals/golden/<id>/`，写报告到 gitignore 目录（如 `evals/reports/`）。

**理由：** Change 2 拒 LC Retriever 是为了归因；RAGAS 当打分库不把检索换成 Chain。

**替代：** ragas 进主依赖 → 拒绝。CI 真打分 → 拒绝。

### 6. CI 与离线的分工

**选择：**

| 路径 | 做什么 |
|------|--------|
| `task ci` | 黄金测试集 JSON 可解析；adapter 用 Fake LLM + spy retrieve 填 Sample 字段；`ragas` 不在 lock 的生产/dev 默认组则测不得 `import ragas`（或 skip）；确定性：给定 fake chunks 时 `retrieved_context_ids` 格式正确 |
| 离线 | `uv sync --group eval` + 真 embedder + 真 DeepSeek + 真 GPT 裁判；人工看报告 |

**理由：** 与「pytest 不测文案」一致。

**替代：** CI 装 ragas 跑 Amnesty → 拒绝（密钥、费用、非本域）。

### 7. 无新表、无新 HTTP

Eval 店是普通 catalog 店铺行 + PG chunk，归属仍 catalog / ai 读库已有表。不新增业务表。

跨域：seed → `catalog.service`（开店/商品）+ 可选 `media.service`；reindex → 已有 `reindex_shop`（经 `app.ai.deps.build_media_service`）。Runner → 仅 `retrieve_chunks` + prompt/LLM。

## Risks / Trade-offs

- [GPT 裁判 vs 中文资料偏差] → 报告注明 judge 模型；第一刀不调阈值。
- [reindex 后 id 失效] → snapshot_id 强制；升版本 checklist。
- [ragas 传递依赖膨胀] → 锁在 eval 组。
- [20–40 条覆盖窄] → 先有趋势仪，不加自动生成集。
- [handler 与 eval 填模板两处] → 同 prompt id；漂移再抽函数。

## Migration Plan

- 无运行时迁移。合入后 CI 行为：多若干不连裁判的测。
- 回滚：删 `evals/` 与 eval 组即可，客服路径无耦合。

## Open Questions

无。探索已拍：叶子、两指标、人手集、Eval 店 id 冻、GPT 裁判、可选依赖、CI 不打分。
