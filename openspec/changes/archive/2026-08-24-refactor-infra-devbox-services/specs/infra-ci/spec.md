## MODIFIED Requirements

### Requirement: Local Allure report tasks

Taskfile SHALL 提供 `test:reports` 与 `latest:report`。`test:reports` SHALL 依赖聚合 **`db:up`**（三库就绪），运行全量或 CLI 传入路径的 pytest 并写入 `reports/allure-results/`，随后 generate HTML 至 `reports/allure-report/`。`latest:report` SHALL 打开 `reports/allure-report/`（须先存在）。

#### Scenario: test:reports 写入 reports 目录

- **WHEN** 开发者在三库就绪后执行 `devbox run -- task test:reports`
- **THEN** SHALL 创建或更新 `reports/allure-results/` 与 `reports/allure-report/`

#### Scenario: latest:report 无报告时失败

- **WHEN** 开发者未运行 `test:reports` 即执行 `latest:report`
- **THEN** task SHALL 以非零退出码失败并提示先运行 `test:reports`

#### Scenario: reports 不入库

- **WHEN** 查看 `.gitignore`
- **THEN** SHALL 忽略 `reports/` 目录

### Requirement: Local ci task includes format check

`task ci` SHALL 在 `task ruff` 之前（或等价顺序）执行 **`task format:check`**，随后 `task ruff`、`task check-test-imports`、`task check-app-layer-discipline`、**`task migrate:all`**、**`task test`**。`task ci` SHALL 通过 **`deps`** 仅声明聚合 **`db:up`**，在本地执行前确保三库就绪。**`task test` 本身 SHALL NOT** 声明 devbox 服务 deps（供 CI 直接调用）。

#### Scenario: 本地 ci 含 format check

- **WHEN** 开发者执行 `devbox run -- task ci` 且存在未格式化 Python 文件
- **THEN** `task ci` SHALL 在 pytest 之前因 `format:check` 失败而退出

#### Scenario: 本地 ci 自动启动三库

- **WHEN** 开发者执行 `devbox run -- task ci` 且 MySQL/Redis/PostgreSQL 未运行
- **THEN** Task deps SHALL 触发聚合 `db:up` 后再继续 lint 与 test

#### Scenario: CI 调用 task test 不触发 devbox

- **WHEN** CI test job 执行 `task test`
- **THEN** SHALL NOT 依赖 devbox 的 `db:up` / `mysql:up` / `redis:up` / `pg:up` 脚本
- **AND** SHALL 依赖 workflow `services` 与 healthcheck 提供三库

### Requirement: Local dev task includes Redis

`task dev` SHALL 通过 **`deps`** 仅声明聚合 **`db:up`**，再启动 `uvicorn --reload`，以便本地开发时 `/health/ready`（三库）与 SMS OTP 路径可用。

#### Scenario: dev 启动前三库就绪

- **WHEN** 开发者执行 `devbox run -- task dev` 且本地库未运行
- **THEN** Task deps SHALL 触发 `db:up` 后再启动 uvicorn
