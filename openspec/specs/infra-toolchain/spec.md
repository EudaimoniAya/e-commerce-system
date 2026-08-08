# infra-toolchain Specification

## Purpose
TBD - created by archiving change infra-ruff-style. Update Purpose after archive.
## Requirements
### Requirement: Ruff format local tasks

Taskfile SHALL 提供 `format` 与 `format:check` task。`format` SHALL 执行 `uv run ruff format .`；`format:check` SHALL 执行 `uv run ruff format --check .` 且在存在未格式化文件时以非零退出码失败。

#### Scenario: format task 改写文件

- **WHEN** 开发者执行 `task format` 且某 Python 文件缩进/换行不符合 Ruff formatter
- **THEN** 该文件 SHALL 被 formatter 就地修正

#### Scenario: format check 未格式化时失败

- **WHEN** 开发者执行 `task format:check` 且存在未格式化 Python 文件
- **THEN** task SHALL 以非零退出码失败

### Requirement: Ruff extended lint rules in pyproject

`pyproject.toml` 的 `[tool.ruff.lint]` SHALL 在 Ruff 默认 F/E 基础上 `extend-select` **I**（isort）、**UP**（pyupgrade）、**B006**、**B007**、**B904**（见 change design.md；**不**整包 `B`，不启用 B008/B905）。SHALL 继续 `extend-select` **ANN** 且对 `app/**/*.py` 与 `alembic/**/*.py` 保留 ANN per-file-ignores（tests 强制注解，app/alembic 不强制）。

#### Scenario: import 未排序时 ruff check 失败

- **WHEN** 某 Python 文件 import 顺序违反 isort 规则且未 fix
- **THEN** `uv run ruff check .` SHALL 报告 I 类违规

#### Scenario: app 代码不因 ANN 失败

- **WHEN** `app/` 下某函数缺少类型注解且仅此 ANN 违规
- **THEN** `uv run ruff check .` SHALL NOT 仅因该 ANN 违规而失败

### Requirement: Git blame ignore for mechanical style commits

仓库根目录 SHALL 提供 `.git-blame-ignore-revs`（**纳入 Git 版本库**）。被忽略的 mechanical commit SHALL 以 **完整 SHA 写入该文件内**（一行一 SHA，允许 `#` 注释）；配置类 commit MAY 先入库仅含注释的 stub，mechanical fix 完成后再追加 SHA。README SHALL 说明开发者可执行 `git config blame.ignoreRevsFile .git-blame-ignore-revs` 以在本地 blame 中跳过这些提交。

#### Scenario: blame ignore 文件存在

- **WHEN** 查看仓库根目录
- **THEN** SHALL 存在 `.git-blame-ignore-revs`
- **AND** infra-ruff-style 全库 mechanical fix 完成后，该文件内 SHALL 至少包含一条对应 commit 的 full SHA

