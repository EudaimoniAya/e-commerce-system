## Why

`test-schema-typing` 与 `test-schema-unit-tests` 已完成 typed Result/Context/builders 与 schema 单测分工，但测试代码仍存在 **分层混乱**：helper 写在 `test_*.py` 或 test 互 import、组合 helper 返回胖 Context、`register_and_open_shop` 与 fixture 边界不清、Arrange/Act 混淆。缺少统一 **测试架构规范** 与 enforcement，AI 与人工会在 test/support/conftest 之间随机放置逻辑。现于 `refactor/test-architecture` 分支收紧分层与数据流，在 **测试场景与断言逻辑不变** 的前提下提升可读性，并保证 CI 全绿。

## What Changes

- 新增全局 capability **`test-architecture`**：四层职责（Case / Fixture / Support / Utilities）、Assert-First、`PipelineResult` 组合容器、`step`/`all` 类型查询、orchestrator 纪律、fail-fast Setup fixture、目录与命名、enforcement（ruff ANN + CI grep）
- **修订** `integration-test-typing`：Context 改为 `root: PipelineResult` 极薄模型；组合 helper 返 `PipelineResult` 而非胖 Context；移除「Context 嵌套 Context」为主模型的要求
- 重构 `tests/support/`：新增 `PipelineResult`、`ProductResult`、`actions.py`（从 conftest 迁 helper）、`seeds.py`；`bearer_headers` 等投影函数
- 重构 `tests/conftest.py`：fixture 仅装配 + fail-fast；helper 迁至 support
- 重构 `tests/user/`、`tests/catalog/`：移除 test 内 helper 与 test 互 import；补全 `client: AsyncClient` 等注解；Act 可见、Act 结果不进 Context
- 目录调整：运维探针迁至 `tests/ops/`（health、readiness、migration smoke）
- 新增 `docs/troubleshooting/测试架构-旧模式反模式记录.md`：记录 refactor 前签名与调用关系（仅签名）
- 新增 Cursor rule `.cursor/rules/test-architecture.mdc`
- **BREAKING**（测试内部）：`ShopOwnerContext` 等字段访问路径变更（如 `shop_owner.shop` → `shop_owner.root.step(ShopResult).body`）；`register_and_open_shop` 返回类型由 `ShopOwnerContext` 改为 `PipelineResult`

## Non-goals

- 不修改 `app/` 业务代码、API 契约或数据库 migration
- 不改变 integration / unit **测试场景与业务断言语义**（仅结构与可读性）
- conftest lazy import app
- `task test:unit` / CI 拆 job（unit 少，本地手动即可）
- 通用 ActionTree / 字符串 helper 名查询 / `payload: Any`
- 为简单 GET 强制 action helper（Act 可 inline `client.get`）
- 同 Pipeline 内 `step(Type, index=)`（MVP 用 `step` + `all`；index 参数后续再加）

## Capabilities

### New Capabilities

- `test-architecture`：测试四层架构、PipelineResult 数据流、Case/Support/Fixture 纪律、orchestrator 与 Arrange/Act 边界、fail-fast、目录、命名与 enforcement

### Modified Capabilities

- `integration-test-typing`：Context 改为 `root: PipelineResult`；组合 orchestrator 返 PipelineResult；helper 不返 Context；Setup fixture fail-fast；修订 shop_owner 等访问方式

## Impact

- **业务域**：无运行时变更；测试触及 **user**、**catalog** 域 integration 用例及 **infra** 探针目录
- **测试**：`tests/support/`、`tests/conftest.py`、`tests/user/`、`tests/catalog/`、`tests/ops/`（自 health/infra 迁入）、`tests/unit/`（仅 import 路径若受影响）
- **文档与规范**：`openspec/specs/test-architecture/`、`openspec/specs/integration-test-typing/`、`.cursor/rules/test-architecture.mdc`、`docs/troubleshooting/测试架构-旧模式反模式记录.md`
- **工具链**：`pyproject.toml`（ruff ANN）、`Taskfile.yml` 或 CI 脚本（grep 禁止 test 互 import）
- **API / 依赖**：无
