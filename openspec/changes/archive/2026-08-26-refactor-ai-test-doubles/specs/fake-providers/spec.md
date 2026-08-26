# fake-providers

## ADDED Requirements

### Requirement: Production rejects mock llm and embedding providers

当 `APP_ENV` 为 `production` 时，系统 SHALL NOT 以 `LLM_PROVIDER=mock` 或 `EMBEDDING_PROVIDER=mock` 完成启动。SHALL 在应用工厂或 Settings 校验阶段抛出明确错误（指明哪个 provider）。`APP_ENV` 为 `development` 或 `test` 时 SHALL 允许上述 mock 值。本 requirement SHALL NOT 因短信假发送类存在而拒绝 production 启动。

#### Scenario: production 且 LLM mock 启动失败

- **WHEN** `APP_ENV=production` 且 `LLM_PROVIDER=mock`
- **THEN** 应用启动或 Settings 校验 SHALL 失败并给出明确错误

#### Scenario: production 且 embedding mock 启动失败

- **WHEN** `APP_ENV=production` 且 `EMBEDDING_PROVIDER=mock`（即使 LLM 为非 mock）
- **THEN** 应用启动或 Settings 校验 SHALL 失败并给出明确错误

#### Scenario: test 环境允许 mock

- **WHEN** `APP_ENV=test`（或 pytest 默认非 production）且 llm/embedding 为 `mock`
- **THEN** SHALL NOT 因此拒绝启动

### Requirement: AI domain testkit directory exists

系统 SHALL 提供目录 `tests/ai/testkit/`。若本 change 尚无跨文件共用替身，该目录 SHALL 至少含 `.gitkeep`。共享替身（≥2 个测试文件）SHALL 放此目录且类名不带前导下划线。

#### Scenario: testkit 目录可被仓库跟踪

- **WHEN** 检查 `tests/ai/testkit/`
- **THEN** 目录存在且至少有一个被 git 跟踪的文件（`.gitkeep` 或替身模块）
