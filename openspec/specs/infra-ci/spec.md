# infra-ci Specification

## Purpose

CI/CD Validate 层：`test.yaml`（Run Tests）paths-filter、lint 与 test 分离、单 job 全量 `task test`、`workflow_dispatch` 手动全量、test-failure-alert、uv 依赖缓存、Allure artifact；废止 domain matrix 与 Taskfile 分域子命令。
## Requirements
### Requirement: CI paths filter for test workflow

GitHub Actions test workflow（`test.yaml`）SHALL 使用 `dorny/paths-filter`（或等价）读取 `.github/utils/file-filters.yaml`，定义至少一个 `code` 过滤器，匹配业务代码与测试相关路径（含 `app/**`、`tests/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`Taskfile.yml` 等）。`lint` 与 `test` job SHALL 仅在 PR/push 变更命中 `code` 时运行。

#### Scenario: 仅 docs 变更跳过 test

- **WHEN** pull_request 仅修改 `docs/**` 或 `openspec/**` 且未命中 `code` 路径
- **THEN** `lint` 与 `test` job SHALL 被 skip
- **AND** workflow SHALL NOT 启动 mysql/redis services

#### Scenario: 业务代码变更触发全量 test

- **WHEN** pull_request 或 push 到 dev/main 变更命中 `code` 路径（如 `app/user/service.py`）
- **THEN** `lint` job SHALL 运行
- **AND** `test` job SHALL 运行全量 pytest（等价 `task test`）

### Requirement: CI test failure alert job

test workflow SHALL 提供 `test-failure-alert`（或等价命名）job，在 `filter`、`lint` 或 `test` job 因 failure 或 cancelled 结束时以非零退出码失败，以便 branch protection 在上游失败时阻塞合并。

#### Scenario: test job 失败时 alert 失败

- **WHEN** `test` job 因 pytest 失败而失败
- **THEN** `test-failure-alert` job SHALL 运行并 exit 1

#### Scenario: 全部 skip 时 alert 不失败

- **WHEN** 变更未命中 `code` 且 `lint`/`test` 均被 skip
- **THEN** `test-failure-alert` job SHALL NOT 因 skip alone 而 fail

### Requirement: CI test workflow naming

Validate 层 test workflow 文件 SHALL 命名为 `.github/workflows/test.yaml`，workflow `name` SHALL 为 `Run Tests`。

#### Scenario: workflow 文件与 display name

- **WHEN** 查看 `.github/workflows/test.yaml`
- **THEN** 首行 `name:` SHALL 为 `Run Tests`
- **AND** 旧文件 `ci.yml` SHALL NOT 存在

### Requirement: CI full test single job

GitHub Actions SHALL 提供单个 `test` job（**无** `strategy.matrix.domain`），声明 **mysql + redis + postgres** services、创建 `ecommerce_test`、执行 MySQL `alembic upgrade head`、执行 AI 库 `alembic -c alembic_ai.ini upgrade head`（或等价 `task migrate:all` 中的 AI 部分）、设置与现 CI 一致的 env（含 `SMS_OTP_FIXED_CODE`、`AI_DATABASE_URL`、`EMBEDDING_PROVIDER=mock`、`EMBEDDING_DIMENSION`），并运行**全量** pytest（**SHALL** 通过 `task test` 执行，与本地一致；Allure 原始结果由 workflow 层 `PYTEST_ADDOPTS` 注入，不另增 Taskfile 子命令）。

#### Scenario: 全量 pytest 无域子集

- **WHEN** `test` job 在命中 `code` filter 后运行
- **THEN** SHALL 收集并执行 `tests/` 下全部用例（含 `tests/user`、`tests/catalog`、`tests/ordering`、`tests/infra`、`tests/ops`、`tests/unit`）
- **AND** SHALL NOT 按 domain 拆分多个 matrix job

#### Scenario: test job 声明 postgres service

- **WHEN** 查看 `.github/workflows/test.yaml` 的 `test` job
- **THEN** SHALL 声明 `services.postgres` 且配置 healthcheck（`pg_isready`）
- **AND** SHALL 在 pytest 前执行 AI 库 migrate

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

### Requirement: ripgrep for check-test-imports

`task check-test-imports`（`scripts/check_no_test_cross_imports.sh`）SHALL 使用 **`rg`（ripgrep）** 在 `tests/**/*.py` 中检查禁止的 test 模块互 import 模式。凡执行该 Task 的环境 **SHALL** 提供可执行的 `rg` 命令：

- **CI lint job**：SHALL 在运行 `task check-test-imports` **之前**显式安装 ripgrep（如 `apt-get install ripgrep`），**SHALL NOT** 仅依赖 runner 镜像可能预装的 `rg`
- **本地 devbox**：SHALL 在 `devbox.json` `packages` 中包含 `ripgrep`（或文档规定的等价 devbox 包），使 `devbox run -- task check-test-imports` 成功

#### Scenario: lint job 安装 ripgrep 后执行 check-test-imports

- **WHEN** CI `lint` job 运行且尚未安装 `rg`
- **THEN** job SHALL 先安装 ripgrep
- **AND** 随后 `task check-test-imports` SHALL 退出码 0（无违规 import 时）

#### Scenario: devbox 内 check-test-imports 可找到 rg

- **WHEN** 开发者在 devbox 环境中执行 `devbox run -- task check-test-imports`
- **THEN** `command -v rg` SHALL 成功
- **AND** 脚本 SHALL NOT 因 `Command 'rg' not found` 失败

### Requirement: CI uv dependency cache

CI workflow SHALL 使用 `actions/cache`（或等价）缓存 uv 下载目录（如 `~/.cache/uv`），cache key SHALL 绑定 `uv.lock` 哈希。

#### Scenario: lock 未变时复用 cache

- **WHEN** 连续两次 CI 运行且 `uv.lock` 内容相同
- **THEN** 第二次 `uv sync` SHALL 可命中 cache 以减少下载时间

### Requirement: CI workflow_dispatch full test

test workflow SHALL 支持无输入的 `workflow_dispatch`，在选定 ref 上运行全量 `lint` + `test`（等价 `task test`），且 SHALL 跳过 paths-filter（强制 `code=true`）。**SHALL NOT** 提供 `domain` 等域筛选输入。

#### Scenario: 手动触发全量 test

- **WHEN** 开发者通过 GitHub UI 或 `gh workflow run "Run Tests" --ref <branch>` 触发 workflow_dispatch
- **THEN** `lint` 与 `test` job SHALL 运行（不 skip）
- **AND** `test` job SHALL 执行全量 pytest（等价 `task test`）

#### Scenario: workflow_dispatch 绕过 paths-filter

- **WHEN** workflow_dispatch 触发且 ref 上仅有 docs 变更
- **THEN** `lint` 与 `test` job SHALL 仍运行（不因 paths-filter 跳过）

### Requirement: CI Allure results artifact

test job SHALL 以 `pytest --alluredir=<dir>` 收集 Allure 原始结果，并在 job 结束时 upload artifact，命名 SHALL 为 `allure-results`（或等价单一名称，**不**要求域后缀），保留期 SHALL ≥ 7 天。

#### Scenario: test job 上传 allure-results

- **WHEN** test job 完成 pytest
- **THEN** SHALL 存在可下载的 artifact 含 Allure JSON 结果
- **AND** artifact 名称 SHALL 为 `allure-results` 或文档约定等价名

### Requirement: Local Allure report tasks

Taskfile SHALL 提供 `test:reports` 与 `latest:report`。`test:reports` SHALL 依赖 **MySQL、Redis 与 PostgreSQL** 就绪（`db:up` + `redis:up` + `pg:up`），运行全量或 CLI 传入路径的 pytest 并写入 `reports/allure-results/`，随后 generate HTML 至 `reports/allure-report/`。`latest:report` SHALL 打开 `reports/allure-report/`（须先存在）。

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

`task ci` SHALL 在 `task ruff` 之前（或等价顺序）执行 **`task format:check`**，随后 `task ruff`、`task check-test-imports`、`task check-app-layer-discipline`、**`task migrate:all`**、**`task test`**。`task ci` SHALL 通过 **`deps`** 声明 `db:up`、`redis:up` 与 `pg:up`，在本地执行前确保三库就绪。**`task test` 本身 SHALL NOT** 声明 devbox 服务 deps（供 CI 直接调用）。

#### Scenario: 本地 ci 含 format check

- **WHEN** 开发者执行 `devbox run -- task ci` 且存在未格式化 Python 文件
- **THEN** `task ci` SHALL 在 pytest 之前因 `format:check` 失败而退出

#### Scenario: 本地 ci 自动启动三库

- **WHEN** 开发者执行 `devbox run -- task ci` 且 MySQL/Redis/PostgreSQL 未运行
- **THEN** Task deps SHALL 触发 `db:up`、`redis:up` 与 `pg:up` 后再继续 lint 与 test

#### Scenario: CI 调用 task test 不触发 devbox

- **WHEN** CI test job 执行 `task test`
- **THEN** SHALL NOT 依赖 devbox 的 `db:up`/`redis:up`/`pg:up` 脚本
- **AND** SHALL 依赖 workflow `services` 与 healthcheck 提供三库

### Requirement: Local dev task includes Redis

`task dev` SHALL 通过 **`deps`** 声明 `db:up` 与 `redis:up`，再启动 `uvicorn --reload`，以便本地开发时 `/health/ready` 与 SMS OTP 路径可用。

#### Scenario: dev 启动前 Redis 就绪

- **WHEN** 开发者执行 `devbox run -- task dev` 且 Redis 未运行
- **THEN** Task deps SHALL 触发 `redis:up` 后再启动 uvicorn

