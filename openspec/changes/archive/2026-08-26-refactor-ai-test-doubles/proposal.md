## Why

Change 3 合并后，产品侧假实现都叫 `Mock*`（`MockLLMClient`、`MockEmbedder`、`MockSmsProvider`），测试里 `_Fake*` 又装了 Stub/Spy/Fake 多种角色，和 ADR-015 / `.cursor/rules/test-doubles.mdc` 的命名冲突。规范文档已在 `origin/dev`（ADR-015）；本刀做两件事：收紧规范里会误导 AI 的措辞（频率、主链、档 1 条件），再做**一次性迁移动作**。避免入口形态那刀（ADR-014）把测试卫生和 HTTP 契约搅在一起。

短标签 `[test-doubles]`。分支：`refactor/ai-test-doubles`。

## What Changes

- **产品侧三类假实现改名**：`MockLLMClient` → `FakeLLMClient`；`MockEmbedder` → `FakeEmbedder`；`MockSmsProvider` → `FakeSmsProvider`。配置值仍为 `mock`（选择空间里就是这个词，不改 `LLM_PROVIDER` / `EMBEDDING_PROVIDER`）。
- **生产快速失败**：`APP_ENV=production` 且 `LLM_PROVIDER=mock` 或 `EMBEDDING_PROVIDER=mock` 时，启动即抛错，禁止静默用假实现。pytest / CI / development 仍可用 mock。
- **规范措辞收紧**（mdc / ADR-015 / 踩坑对照表）：测试侧频率按个数写 Stub/Spy 最常见；「逻辑」排除仅记录；混合角色归 Spy 但优先复用产品 Fake；档 1 在无产品假实现时是正确默认；`_Never*` 不是 Dummy；纯数据载体不进五类；档 2 仅在选了开箱即用时相对档 3 首选。
- **AI 测试卫生**：按踩坑记录「改后名字」表执行——`_FakeLLM` / `_FakeGenerationLLM` 删除并注入 `FakeLLMClient`；`_FakePromptLoader` 保持；数据载体去掉 Fake 前缀。新建 `tests/ai/testkit/`（暂时无跨文件共用替身则只放 `.gitkeep`）。
- **活 spec / architecture / ADR-002 表**同步产品类名。archived change 文档不改。

## Capabilities

### New Capabilities

- `fake-providers`：生产环境禁止选用 llm/embedding 的 mock；`tests/ai/testkit/` 占位目录。

### Modified Capabilities

- `ai-support-agent`：LLM 假实现类名改为 `FakeLLMClient`；配置键值仍为 `mock`。
- `infra-ai-pgvector`：`MockEmbedder` 改为 `FakeEmbedder`；配置值仍为 `mock`。
- `user-auth`：短信假发送类名改为 `FakeSmsProvider`（仍硬编码调用，不引入 provider 协议）。

## Non-goals

- **不做** AI HTTP 入口 / 删除 Port / PATCH / `handler_mode` 分派（ADR-014，下一刀）。
- **不做** 短信协议注入或真实网关（档 4 升级留给独立 change）。
- **不做** 把配置值 `mock` 改成 `fake`。
- **不做** 因短信无配置项而在 production 拦启动（否则当前唯一实现会让所有 prod 起不来）。
- **不改** archived OpenSpec 历史正文。

## Impact

- **域**：`ai`（LLM 类名、deps）、`infra`（Embedder 类名、生产门禁）、`user`（Sms 类名）、`tests/ai`。
- **API**：无 HTTP 契约变更。
- **BREAKING（仅生产配置）**：`APP_ENV=production` 时不得再配 llm/embedding 为 `mock`。
- **测试**：CI 仍 `EMBEDDING_PROVIDER=mock`、`LLM_PROVIDER=mock`、`APP_ENV` 非 production。
