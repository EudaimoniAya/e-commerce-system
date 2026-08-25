## 1. TDD — 失败测试（红）

> 只写测、不写实现。§1 完成前不得开始 §2–§7。

- [x] 1.1 扩展 `tests/testkit/helper/support.py`：`patch_buyer_handler_mode`；必要时扩展 Result 类型。更新既有「lazy create 后 `handler_mode==human`」断言为期望 `ai`（将失败直至改默认）
- [x] 1.2 编写 `tests/support/test_handler_mode.py`：PATCH `human`/`ai` 200、无会话 404、非法值 422、401；`handler_mode=human` 时 POST 不新增 `author_role=ai`；店主 inbox POST 不触发 AI 行；**不编写** PATCH 路由与 Port
- [x] 1.3 编写 `tests/support/test_ai_turn.py`：注入 Mock Port 返回固定文案时买家 POST 201 仍为买家行，GET messages 含随后 `author_role=ai` 且 `sender_role=shop`；Port 抛错时买家仍 201 且有兜底助手行；未注入工厂不 500；**不编写** service 接线
- [x] 1.4 编写 `tests/ai/`：τ 纯函数边界；注册表仅 `{knowledge}`；Mock LLM 输出 unknown / 低置信 → 不调用 retrieve（mock）；`knowledge`+高置信按 0/1/多 ref 把 `product_id` 传给 retrieve mock；空 retrieve 不调生成 LLM；提示词按 id 加载、缺 id 报错；**不编写** agent / loader 实现
- [x] 1.5 编写 `tests/infra/test_embedder_vendor.py`：httpx mock 下 `zhipu`/`dashscope` 返回 1024 维；**不编写** 真 HTTP 实现（现状 `NotImplementedError` 即为红）
- [x] 1.6 `devbox run -- task db:up` 后跑 §1.1–1.5 相关 pytest，确认失败（红）

## 2. 配置、提示词与 LLM（绿）

- [x] 2.1 Settings：`LLM_PROVIDER`（`mock`|`deepseek`）、`LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`、`TAU_THRESHOLD`（默认 0.3）；`.env.example` / CI 默认 mock
- [x] 2.2 `app/ai/prompts/` 登记 `nlu_route`、`rag_answer`、`suggest_human`（`id`+`version`+`template`）+ 加载器
- [x] 2.3 `LLMClient` 协议、`MockLLMClient`、`DeepSeekClient`（httpx；单测 mock HTTP，不打真网）
- [x] 2.4 跑绿 §1.4 中 prompt / LLM / τ 用例

## 3. 客服 agent（绿）

- [x] 3.1 IntentRegistry + IntentController；只注册 `knowledge`；NL 网关读 `nlu_route`；低于 τ 或非 knowledge → `suggest_human` 文案且不 retrieve
- [x] 3.2 知识 handler：`retrieve_chunks` + ref 规则（0/`None`、1、多→最后）；空列表拒答不生成；生成走 `rag_answer` + LLM；日志带 `prompt_id`/`version`
- [x] 3.3 `app/ai/deps.py`：`build_llm_client`、`build_prompt_loader`、`build_buyer_turn_handler`
- [x] 3.4 跑绿 §1.4 其余 agent / 注册表 / product_id 用例

## 4. support Port、默认 AI、PATCH（绿）

- [ ] 4.1 `app/support/ports.py` 的 `BuyerTurnAiHandler`；service 可选注入；`deps.register_buyer_turn_handler_factory`（**不** import `app.ai`）
- [ ] 4.2 lazy create `handler_mode=ai`（ORM default 与 server_default）；买家 PATCH 路由；人工模式不调 Port；AI 模式落 `author_role=ai`；preview 用助手截断；Port 失败 / 未注入 → 兜底文案仍 201
- [ ] 4.3 `main.py` 注册 `build_buyer_turn_handler` 工厂
- [ ] 4.4 跑绿 §1.1–1.3 与既有 `tests/support/`（店主回复仍 `author_role=human`）

## 5. Embedder 真厂商 HTTP（绿）

- [ ] 5.1 实现 `ZhipuEmbedder` / `DashscopeEmbedder` 的 `embed_texts`（httpx、维度校验、失败 fail-fast）
- [ ] 5.2 跑绿 §1.5；确认 CI 仍 `EMBEDDING_PROVIDER=mock`

## 6. 文档

- [ ] 6.1 修订 ADR-013 决策 5：首批仅知识检索 + 转人工文案；Tool 类意图随后续 change 注册
- [ ] 6.2 修订 ADR-012 Change 3 行：评测集 / τ 标定移出；本刀仅 τ 最小版
- [ ] 6.3 修订 `docs/architecture.md`：support 默认 AI、PATCH、买家 POST 同步 AI 回合、无 `/ai/*`

## 7. 本地 CI

- [ ] 7.1 `uv run python scripts/check_app_layer_discipline.py`（support 不得 import ai；无 `app/ai/router.py`）
- [ ] 7.2 `devbox run -- task ci` 全绿

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§5。每个 apply 会话建议只完成 1 个 Task 节。archived change2 的 Decision 12/14 **不改历史文件**。
