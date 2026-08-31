## 1. TDD — 失败测试（红）

> 只写测、不写实现。§1 完成前不得开始 §2–§5。评测接线测放 `tests/ai/`（unit 为主），**不要** `@pytest.mark.integration`（不连裁判、不要求三库）。**不编写** `app/ai/evals/`、`evals/golden/`、`pyproject.toml` 的 eval 组。红项引用的模块路径以红节测试文件为准（本刀统一落 `app/ai/evals/` 包内）。

- [x] 1.1 黄金测试集：断言仓库内 `evals/golden/<snapshot_id>/samples.jsonl` 存在，行数 20–40（含）；每行含 `id`、`question`、`shop_id`；`product_id` 允许 JSON `null`；至少一条 `product_id` 为非空 UUID 字符串；样本 SHALL NOT 要求会话消息 / HTTP 字段。**不创建** jsonl
- [x] 1.2 同上文件：凡含 `reference_context_ids` 的样本，每项匹配 `{document_id}:{chunk_index}` 且 `chunk_index` 为非负整数；每条至少有 `reference` 或非空 `reference_context_ids` 之一。**不填写** 应召回 id
- [x] 1.3 `evals/golden/<snapshot_id>/manifest.yaml`：含与目录名一致的 `snapshot_id`；含 Eval 店 `shop_id` 或可重建种子标识；与 pytest 临时店数据分离（manifest 不得指向 `clean_ai_chunks` 类 fixture 店）。**不编写** manifest
- [x] 1.4 叶子 adapter：注入 Fake 检索返回带 `document_id` / `chunk_index` / `content_text` 的 chunk 列表后，产出 `retrieved_contexts` 与 `content_text` 顺序一致，`retrieved_context_ids` 为 `document_id:chunk_index`；检索经 `retrieve_chunks`（**不** import LangChain Retriever 作检索实现）；`product_id is None` 时调用检索不传商品过滤。**不编写** adapter
- [x] 1.5 同上：有 chunk 时 SHALL 调 `LLMClient.generate`，且模板经 `build_prompt_loader().load("rag_answer")` 登记（mock loader 断言 `load("rag_answer")` 被调，chunks 与问句按该模板填写）。**不编写** 生成分支
- [x] 1.6 同上：检索返回空列表时 SHALL NOT 调用 `LLMClient.generate`，`response` 等于 `build_prompt_loader().load("suggest_human").text`。**不编写** 空检索分支
- [x] 1.7 同上：跑 adapter 时 SHALL NOT 实例化 `IntentController` / 调用 `handle_buyer_turn`，SHALL NOT 对 `/ai/shops/{shop_id}/replies` 发 HTTP（可用 import 探测 + 无 AsyncClient）。**不编写** HTTP 绕行
- [x] 1.8 离线指标清单（常量或 `enabled_metrics()` 一类纯函数，落 `app/ai/evals/`）：名称含 faithfulness 与 context_recall（或 RAGAS 类名等价），不含 context_precision / answer_relevancy。**不编写** 指标模块
- [x] 1.9 裁判与生成分离：config/Settings 可读独立变量 `RAGAS_JUDGE_API_KEY` / `RAGAS_JUDGE_BASE_URL` / `RAGAS_JUDGE_MODEL`（与生成 `LLM_*` 不同名）；缺省（env 未设）时 Settings 构造不抛错、评测相关 pytest 仍绿。**不编写** 裁判配置
- [x] 1.10 `devbox run -- uv run pytest`（或等价）跑 §1.1–1.9 相关文件，确认失败（红）

## 2. 可选依赖与裁判配置（绿）

- [x] 2.1 `pyproject.toml` 增加 `[dependency-groups] eval`（含 `ragas`）；生产 `dependencies` 不加 ragas。`.env.example` 注释 `RAGAS_JUDGE_API_KEY` / `RAGAS_JUDGE_BASE_URL` / `RAGAS_JUDGE_MODEL`（仅离线、不进 CI）。Settings 可读裁判项但缺省不得让 `task ci` 失败
- [x] 2.2 跑绿 §1.9

## 3. 叶子 adapter（绿）

- [ ] 3.1 实现 `app/ai/evals/`：对样本调用 `retrieve_chunks`；填 `retrieved_contexts` / `retrieved_context_ids`；有 chunk 时用 `rag_answer` + `LLMClient.generate`；空检索用 `suggest_human` 正文且不调生成。**不**调用 `IntentController` / `/ai/replies`
- [ ] 3.2 跑绿 §1.4–1.7

## 4. Eval 店种子与黄金测试集（绿）

- [ ] 4.1 种子脚本：经 **catalog.service**（及如需 **media.service**）写入独立 Eval 店与 2–3 个可区分事实的商品；再走已有 `reindex_shop`（组合根经 `app.ai.deps.build_media_service`）。禁止 catalog/media ORM。目标为 **dev** 库，勿与 `clean_ai_chunks` 测试店混用
- [ ] 4.2 提交 `evals/golden/<snapshot_id>/manifest.yaml` + `samples.jsonl`（20–40 条）：问句人手写；`reference` 和/或 reindex 后对照 PG 填写 `reference_context_ids`；覆盖有 `product_id`、整店泛问、资料没有的易幻觉问
- [ ] 4.3 跑绿 §1.1–1.3

## 5. 离线 RAGAS runner（绿）

- [ ] 5.1 `python -m app.ai.evals.runner`（或等价）：读当前快照黄金测试集 → adapter → RAGAS Faithfulness + Context recall；生成用 `LLM_*`（DeepSeek），裁判用 `RAGAS_JUDGE_*`。报告写入 gitignore 目录（如 `evals/reports/`，确认 `.gitignore` 已覆盖、不进库）。**不**把 runner 挂进 `task ci`
- [ ] 5.2 跑绿 §1.8（指标集合）。本会话可用 mock/跳过真打分；真密钥手验不作为 CI 门禁

## 6. 本地 CI

- [ ] 6.1 `devbox run -- task ci` 全绿（无裁判密钥、未 `uv sync --group eval` 亦须绿）

## 7. 文档整理

- [ ] 7.1 修订 ADR-012：评测路径由「change 3 移出」改为本刀落地（黄金测试集 + 叶子 RAGAS 两指标）；τ 标定仍不在本刀；更新 change 表状态（2.1 / 3 已归档）
- [ ] 7.2 修订 `docs/architecture.md` 客服质量补一句离线 RAGAS（可选组、不进默认 CI）；同步 `ai-rag-retrieval` 的 delta 修订（检索集成测仍不依赖 ragas；评测为可选组、入口仍是 `retrieve_chunks`）。**不改** `openspec/changes/archive/**`

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§5。每个 apply 会话建议只完成 1 个 Task 节。短标签 `[ragas-eval]`。
