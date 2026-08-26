## Context

- ADR-015 与 `test-doubles.mdc` 已在 `origin/dev`（规范先行）。本刀补两处：收紧会误导 AI 的规范措辞，再做迁移清单。
- 产品假实现：`MockLLMClient`（已带 `calls`，实质 Fake+记录）、`MockEmbedder`、`MockSmsProvider`（`send_otp` 内硬编码调用）。
- `tests/ai/test_intent_controller.py` 等处 `_FakeLLM` 与产品 `MockLLMClient` 重复；同文件还有 Spy / Fake / 数据载体混用 `_Fake*` 前缀。
- 约束：配置值 `mock` 不改；短信不升级协议；不碰 ADR-014 入口。
- 分支：`refactor/ai-test-doubles`；短标签 `[test-doubles]`。

## Goals / Non-Goals

**Goals:**

- 三类产品假实现类名统一 `Fake*`。
- `APP_ENV=production` 时 llm/embedding 选 `mock` 启动失败。
- 收紧 mdc / ADR-015 措辞（频率按个数、主链排除纯记录、档 1 条件冗余）。
- AI 测试按「改后名字」表改名/复用；`tests/ai/testkit/.gitkeep` 占位。

**Non-Goals:**

见 proposal.md（入口形态、短信协议、改配置词、archive 改写、因短信拦 prod）。

## Decisions

### 1. 类名改 Fake*，配置值仍是 mock

**选择**：Python 标识符 `FakeLLMClient` / `FakeEmbedder` / `FakeSmsProvider`。环境变量仍 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=mock`。`deps` / `get_embedder` 的分支判断字符串不改。

**理由**：拍板「选择空间里只有 mock」；CI、`.env.example`、infra-ci spec 已写死 `mock`。类名解决「Mock 一词占用」；配置词保持稳定。

**替代**：配置也改成 `fake` → 拒绝，无新选项却全库改 env。

### 2. 生产快速失败只覆盖有配置开关的假实现

**选择**：新增 `reject_mock_providers_in_production(settings)`（放 `app/infra/config.py`，与 Settings 同模块）。若 `app_env == "production"` 且（`llm_provider == "mock"` 或 `embedding_provider == "mock"`）→ raise `ValueError`（文案含 `production` 与哪个 provider）。`create_app()` 在 `get_embedder()` **之前**调用。单测 monkeypatch 已加载的 Settings，**不**启全应用。`development` / `test` 不拦。

短信：本刀只改类名。无 `SMS_PROVIDER`；生产门禁 **SHALL NOT** 因 `FakeSmsProvider` 拒启动。

**理由**：档 2 要求「生产选中假实现必须快速失败」。短信若同样拦，当前硬编码假发送会让所有 production 起不来，等于偷偷做方案 C。

**替代**：给短信立刻加协议 + 真网关 → 拒绝，超出本刀。`app_env=prod` 才拦，不用 `APP_ENV_FILE` 判断（测试也读 `.env.test`）。

### 3. AI 测试：复用 FakeLLMClient；数据载体不是替身；testkit 先占位

**选择**：按踩坑记录「改后名字」表执行（混合 Stub+记录归 Spy，但能复用产品 Fake 则不新造 `_SpyLLM`）：

| 现名 | 改后 |
|---|---|
| `_FakeLLM` / `_FakeGenerationLLM` | 删除，注入 `FakeLLMClient` |
| `_make_retrieve` | 可改名 `_spy_retrieve`；不必升格成类 |
| `_FakePromptLoader` | 保持（单文件 Fake：查表 + KeyError） |
| `_FakeChunk` / `_FakeLoadedPrompt` | 去掉 Fake 前缀，直接构造（不是替身） |
| `_NeverGenerationLLM` | 保持 `_Never*` |

≥2 文件共用才进 `tests/ai/testkit/`。本刀若仍无共用，目录只放 `.gitkeep`。

**理由**：mdc 复用优先 + 混合取 Spy + 数据载体不进五类。空 testkit 是拍板占位，不是投机模块。

### 4. 活文档同步，archive 不动

**选择**：改 `openspec/specs/` 下 ai-support-agent / infra-ai-pgvector / user-auth，以及 `architecture.md`、ADR-002 表格里的类名。`openspec/changes/archive/**` 不改。

## Risks / Trade-offs

- [生产部署若仍配 embedding/llm=mock 会起不来] → 这是门禁本意；`.env.example` 注明 production 须真厂商。
- [全局重命名漏改] → ruff/pytest 会红；grep `MockLLMClient` 作收尾。
- [入口那刀仍有 `MockBuyerTurnAiHandler`] → 属 support 测试替身，随 ADR-014 删 Port 一起处理，本刀不改行为测试。

## Migration Plan

- 无表、无数据迁移。
- 回滚：类名改回 + 去掉 production 校验。

## Open Questions

无。
