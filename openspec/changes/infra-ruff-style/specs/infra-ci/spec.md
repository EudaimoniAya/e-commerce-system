## MODIFIED Requirements

### Requirement: CI lint job separation

GitHub Actions workflow SHALL 提供独立 `lint` job，执行 **`task format:check`**、**`task ruff`** 与 **`task check-test-imports`**（或等价命令），**不** 声明 mysql/redis services。`lint` job SHALL 在 paths-filter 命中 `code` 时运行。

#### Scenario: lint job 无数据库依赖

- **WHEN** CI workflow 运行 `lint` job
- **THEN** job SHALL NOT 声明 `services.mysql` 或 `services.redis`
- **AND** SHALL 执行 ruff format check、ruff lint 与 test-import 检查

#### Scenario: lint 与 test 并行

- **WHEN** CI workflow 在 pull_request 或 push 到 dev/main 时触发且命中 `code`
- **THEN** `lint` job 与 `test` job SHALL 可并行启动（test 不 `needs: lint`）

#### Scenario: 未格式化代码导致 lint job 失败

- **WHEN** PR 引入未运行 `ruff format` 的 Python 变更
- **THEN** `lint` job 中 `task format:check` SHALL 失败
- **AND** `test` job MAY 仍并行运行直至自身完成或 workflow 取消

### Requirement: Local ci task includes format check

`task ci` SHALL 在 `task ruff` 之前（或等价顺序）执行 **`task format:check`**，随后 `task ruff`、`task check-test-imports`、`task test`，与远程 lint + test 行为对齐（format + lint 本地一次跑完；test 仍不自动 `db:up`/`redis:up`）。

#### Scenario: 本地 ci 含 format check

- **WHEN** 开发者执行 `task ci` 且存在未格式化 Python 文件
- **THEN** `task ci` SHALL 在 pytest 之前因 `format:check` 失败而退出
