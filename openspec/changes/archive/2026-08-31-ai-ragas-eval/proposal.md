## Why

知识类客服闭环（检索 + 生成 + AI HTTP）已落地，τ 仍是手工 0.3，**没有**对「检回的 chunk 对不对、答案有没有编造」的离线测量。Change 3 把黄金测试集 / RAGAS / τ 标定移出；入口刀明确不改 `retrieve_chunks`。本刀补评测路径（ADR-012 第三条），给后续「加历史 / 改切块 / 换模型」一条可复跑的基线。短标签 `[ragas-eval]`。分支：`feature/ai-ragas-eval`。

## What Changes

- **离线评测跑道**：不改客服运行时（不改 `/ai/replies`、`IntentController`、`assemble_turn`、NLU、τ）。Runner 直接调叶子：`retrieve_chunks` + 与 `rag_answer` 相同的生成（真 DeepSeek，与线上知识 handler 一致）。
- **黄金测试集**：人手 20–40 条单轮样本（术语不用「金标」）。每条含问句、`shop_id`、`product_id`（可空=整店）、参考答案和/或应召回 `document_id+chunk_index`。不跑回看墙、不打 HTTP。
- **Eval 店**：独立于 pytest 随建随清数据的店铺剧本 + 一次 reindex 冻进 PG；管线与黄金测试集同快照版本。快照 id 对齐 `document_id` + `chunk_index`；reindex 后须重对或升版本。
- **RAGAS 指标（第一刀）**：Faithfulness + Context recall。Context precision / Answer（Response）Relevancy **不做**。Agent / LangGraph / 多轮指标 **不做**。
- **裁判 LLM**：另一家 GPT（OpenAI 兼容），与生成用的 DeepSeek 分离；密钥仅离线 env，**不进 CI**。
- **依赖**：`ragas` 进可选依赖组（如 `[dependency-groups] eval`），**不**进生产 `dependencies`。`task ci` **不**跑真打分。
- **CI 可测部分**：黄金测试集可解析、adapter 能填 `SingleTurnSample` 字段、缺 eval extra 时主测试仍绿；可用 Fake 生成测接线，不调裁判。
- **活文档**：ADR-012 评测路径从「移出」改为本刀落地；`architecture.md` 客服质量补一句离线 RAGAS。修订 `ai-rag-retrieval` 中「CI 不依赖 ragas」为：检索集成测仍不依赖；评测为可选组。

## Capabilities

### New Capabilities

- `ai-ragas-eval`：Eval 店与语料快照、黄金测试集形状、叶子 adapter（retrieve + generate）、RAGAS Faithfulness / Context recall 离线打分、可选依赖与 CI 边界。

### Modified Capabilities

- `ai-rag-retrieval`：明确 `retrieve_chunks` 为评测检索入口；主 CI / 检索测仍 SHALL NOT 把 `ragas` 当必装依赖。

## Non-goals

- **不改**客服运行时：router、编排器、回看墙、问候模板、`handler_mode`。商品上下文越过 AI / 2h TTL / 新卡优先 **另刀**。
- **不做** τ 标定、多轮评测、会话历史进 LLM、打 `POST /ai/replies` 黑盒。
- **不做** Context precision、Answer/Response Relevancy、ToolCallAccuracy 等。
- **不做** agent 执行 trace / LangSmith / `convert_to_ragas_messages`。
- **不做** 用 Amnesty QA 等公开集当产品基线（仅允许本地把 API 跑通，分数不入库）。
- **不做** 前端、SSE、LangGraph、计费网关。
- **不改** `retrieve_chunks` 算法、意图注册表（仍仅 `knowledge`）、archived OpenSpec 正文。

## Impact

- **域**：`ai`（evals runner / 黄金测试集 / 可选 ragas）。catalog / media 仅作为 Eval 店 **seed 数据**（走已有 service 或 git 剧本），**无 API 行为变更**。support / ordering / engagement / user / infra **无运行时行为变更**（裁判配置项可落 `Settings`，仅离线读取）。
- **API**：无新 HTTP。
- **依赖**：生产镜像不含 `ragas`；本地 `uv sync --group eval`（名称以 design 为准）。
- **测试**：`tests/ai/` 下评测接线测（不连裁判）；`task ci` 全绿且不要求 OpenAI/GPT 密钥。
