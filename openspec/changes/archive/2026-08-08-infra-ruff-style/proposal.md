## Why

项目已接入 Ruff lint（默认 F/E + tests 的 ANN），但 **未** 启用 `ruff format`、import 排序（I）、语法现代化（UP）与常见 bug 模式（B）等规则，CI 亦只跑 `ruff check`。随着后续 refactor（如 `tests/testkit` 重命名）即将产生大量 mechanical diff，需要先建立 **可执行的 Ruff 风格门禁**，避免格式与 import 噪音淹没 review，并为规范文档提供 CI 背书。

## What Changes

- **Ruff lint 扩展**：保留默认 F/E 与 `tests/` 的 ANN（`app/**`、`alembic/**` 继续 ignore ANN）；新增 `I`（isort）、`UP`（pyupgrade）、`B` 子集（flake8-bugbear，见 design.md 具体规则列表）
- **Ruff format**：新增 `task format`（或等价）与 `ruff format --check` CI 门禁；对全库 Python 一次性 format + lint fix（机械变更，无业务行为变更）
- **CI / 本地**：扩展 `task ci` 与 `.github/workflows/test.yaml` lint job，覆盖 format check + 扩展 lint；README 同步
- **Git blame**：新增 `.git-blame-ignore-revs`，记录全库 format/lint fix 的 mechanical commit SHA；README 说明 `git config blame.ignoreRevsFile`
- **文档**：ADR-008 增补 commit type `style` 与分支前缀 `style/*` 定义；短标签 `[ruff-style]`

## Non-goals

- **不** 重命名 `tests/support` → `tests/testkit`（后续独立 change）
- **不** 启用 mypy 或扩展 `app/**` 的 ANN
- **不** 新增跨域 import 静态检查脚本
- **不** 修改业务 API、数据库 schema 或运行时行为
- **不** 引入 pre-commit（可后续 change 按需添加）

## Capabilities

### New Capabilities

- `infra-toolchain`：Ruff format/lint 规则（pyproject）、Taskfile format task、`.git-blame-ignore-revs` 仓库元配置

### Modified Capabilities

- `infra-ci`：lint job 与本地 `task ci` 须包含 `task format:check`（与 `task ruff`、check-test-imports 一并执行）

## Impact

- **影响域**：`infra`（工具链 / CI）；无 user / catalog / ordering / engagement / support 业务域变更
- **代码**：`pyproject.toml`、`Taskfile.yml`、`.github/workflows/test.yaml`、全库 `*.py`（机械 format/lint fix）、`.git-blame-ignore-revs`、`docs/decision/ADR-008-*.md`、`README.md`
- **分支**：`style/infra-ruff-style`（本 change 定义 `style/*` 前缀，用自身践行；见 design.md 决策 5）
- **依赖**：无新增 Python 依赖（沿用 dev 组 `ruff`）
- **API / DB**：无
