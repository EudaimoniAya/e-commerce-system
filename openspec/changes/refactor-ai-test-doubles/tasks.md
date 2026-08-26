## 1. TDD — 失败测试（红）

> 只写测、不写实现。§1 完成前不得开始 §2–§5。

- [x] 1.1 改 `tests/ai/test_llm_client.py`：import / 构造改为 `FakeLLMClient`；断言 `app.ai.llm.client` **没有** `MockLLMClient`。**不编写**产品类改名
- [x] 1.2 改 `tests/infra/test_embedder.py`、`tests/infra/test_pg.py`：断言 `get_embedder()` 在 `EMBEDDING_PROVIDER=mock` 时类型为 `FakeEmbedder`；`app.infra.embedder` **没有** `MockEmbedder`。**不编写** Embedder 改名
- [x] 1.3 新增短信类名单测：`FakeSmsProvider.send` 可调用；`app.user.sms_service` **没有** `MockSmsProvider`。**不编写**短信类改名、**不**引入 SMS_PROVIDER
- [x] 1.4 新增 `tests/infra/test_production_mock_providers.py`：monkeypatch `Settings`（不调 `create_app`）——`app_env=production` 且 `llm_provider=mock` 时 `reject_mock_providers_in_production` 抛错（文案含 production 与 llm）；embedding 为 mock 时同样失败；`app_env=test` 且两者均为 mock **不**抛。**不编写**校验函数
- [x] 1.5 新增测例：仓库存在可被 git 跟踪的 `tests/ai/testkit/.gitkeep`（或同目录替身模块）。**不创建**该目录
- [x] 1.6 改 `tests/ai/test_intent_controller.py`：NLU / 生成 LLM 注入 `FakeLLMClient`（删 `_FakeLLM` / `_FakeGenerationLLM`）；`_make_retrieve` 可改名 `_spy_retrieve`（不必升格成类）；`_FakePromptLoader` **保持**（单文件 Fake）；`_FakeChunk` / `_FakeLoadedPrompt` **去掉 Fake 前缀**、直接构造（不是替身，**不要**改成 `_Stub*`）。**不编写**产品实现
- [x] 1.7 `devbox run -- task db:up` 后跑 §1.1–1.6 相关 pytest，确认失败（红）

## 2. 产品侧 Fake 改名（绿）

- [x] 2.1 `MockLLMClient` → `FakeLLMClient`（`app/ai/llm/client.py`、`app/ai/deps.py`）；配置值仍为 `mock`
- [x] 2.2 `MockEmbedder` → `FakeEmbedder`（`app/infra/embedder.py`）；配置值仍为 `mock`
- [x] 2.3 `MockSmsProvider` → `FakeSmsProvider`（`app/user/sms_service.py` 调用点同步）；**不**加短信协议 / 配置项
- [x] 2.4 跑绿 §1.1–1.3、§1.6（`devbox run -- uv run pytest tests/ai/test_llm_client.py tests/ai/test_intent_controller.py tests/infra/test_embedder.py tests/infra/test_pg.py -q` 及 §1.3 短信测）

## 3. 生产 mock 门禁（绿）

- [x] 3.1 实现 `reject_mock_providers_in_production`；`create_app()` 在 `get_embedder()` 之前调用。仅拦 llm / embedding 的 `mock`；短信假发送 **不**参与门禁
- [x] 3.2 `.env.example` 注明 `APP_ENV=production` 时不得将 `LLM_PROVIDER` / `EMBEDDING_PROVIDER` 设为 `mock`
- [x] 3.3 跑绿 §1.4

## 4. AI testkit 占位（绿）

- [ ] 4.1 新增 `tests/ai/testkit/.gitkeep`（本刀无跨文件共用替身则不放 Python 模块）
- [ ] 4.2 跑绿 §1.5；`rg 'MockLLMClient|MockEmbedder|MockSmsProvider' app tests --glob '!**/archive/**'` 无产品类残留（注释/文档同步改 Fake）

## 5. 活文档

- [ ] 5.1 修订 `docs/architecture.md`：Embedder / LLM 类名改为 Fake*
- [ ] 5.2 修订 ADR-002 测试表中 `MockEmbedder` 用词为 `FakeEmbedder`
- [ ] 5.3 确认 ADR-015 / `test-doubles.mdc` / 踩坑「改后名字」表与 design 决策 3 一致（测试侧 Stub/Spy 最常见、主链排除仅记录、档 1 条件冗余、数据载体不是替身）。规范正文已在 propose 收紧，apply **不得**写回「Fake ~90%」或把数据载体改成 `_Stub*`。**不改** `openspec/changes/archive/**`

## 6. 本地 CI

- [ ] 6.1 `devbox run -- task ci` 全绿

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§4。每个 apply 会话建议只完成 1 个 Task 节。短标签 `[test-doubles]`。
