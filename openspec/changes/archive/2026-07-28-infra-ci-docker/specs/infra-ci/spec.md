# infra-ci

## Purpose

CI/CD Validate 层增强：lint 与 test 分离、按业务域 matrix 并行 pytest、uv 依赖缓存、workflow_dispatch 域筛选、Allure 测试报告 artifact，以及 Taskfile 本地域测试与报告命令。

## ADDED Requirements

### Requirement: CI lint job separation

GitHub Actions workflow SHALL 提供独立 `lint` job，执行 `task ruff` 与 `task check-test-imports`（或等价命令），**不** 声明 mysql/redis services。

#### Scenario: lint job 无数据库依赖

- **WHEN** CI workflow 运行 `lint` job
- **THEN** job SHALL NOT 声明 `services.mysql` 或 `services.redis`
- **AND** SHALL 执行 ruff 与 test-import 检查

#### Scenario: lint 与 test 并行

- **WHEN** CI workflow 在 pull_request 或 push 到 dev/main 时触发
- **THEN** `lint` job 与 `test` matrix job SHALL 可并行启动（无 `needs: lint` 阻塞 test，或 lint 失败时 workflow 整体失败由 GitHub 汇总）

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

### Requirement: CI test domain matrix

GitHub Actions SHALL 提供 `test` job，使用 `strategy.matrix.domain` 并行运行 pytest，域取值 SHALL 为 `user`、`catalog`、`ordering`、`infra`、`unit`。每个 matrix job SHALL 声明 mysql + redis services、创建 `ecommerce_test`、执行 `alembic upgrade head`、设置与现 CI 一致的 env（含 `SMS_OTP_FIXED_CODE`）。

#### Scenario: user 域 matrix 路径

- **WHEN** matrix `domain=user` job 运行 pytest
- **THEN** SHALL 仅收集并执行 `tests/user/` 与 `tests/unit/user/` 下用例

#### Scenario: catalog 域 matrix 路径

- **WHEN** matrix `domain=catalog` job 运行 pytest
- **THEN** SHALL 仅收集并执行 `tests/catalog/` 与 `tests/unit/catalog/` 下用例

#### Scenario: ordering 域 matrix 路径

- **WHEN** matrix `domain=ordering` job 运行 pytest
- **THEN** SHALL 仅收集并执行 `tests/ordering/` 下用例

#### Scenario: infra 域 matrix 路径

- **WHEN** matrix `domain=infra` job 运行 pytest
- **THEN** SHALL 仅收集并执行 `tests/infra/` 与 `tests/ops/` 下用例

#### Scenario: unit 域 matrix 路径

- **WHEN** matrix `domain=unit` job 运行 pytest
- **THEN** SHALL 仅收集并执行 `tests/unit/` 下用例

### Requirement: CI uv dependency cache

CI workflow SHALL 使用 `actions/cache`（或等价）缓存 uv 下载目录（如 `~/.cache/uv`），cache key SHALL 绑定 `uv.lock` 哈希。

#### Scenario: lock 未变时复用 cache

- **WHEN** 连续两次 CI 运行且 `uv.lock` 内容相同
- **THEN** 第二次 `uv sync` SHALL 可命中 cache 以减少下载时间

### Requirement: CI workflow_dispatch domain filter

workflow SHALL 支持 `workflow_dispatch` 输入 `domain`，可选值 SHALL 包含 `all`、`user`、`catalog`、`ordering`、`infra`、`unit`。当选择非 `all` 时，test matrix SHALL 仅运行对应域一行。

#### Scenario: 手动触发单域 user

- **WHEN** 开发者通过 workflow_dispatch 选择 `domain=user`
- **THEN** test matrix SHALL 仅执行 user 域 pytest job
- **AND** lint job SHALL 仍执行（或文档约定与 `all` 一致）

#### Scenario: 手动触发 all

- **WHEN** workflow_dispatch 选择 `domain=all`
- **THEN** test matrix SHALL 运行全部五个域 job

### Requirement: CI Allure results artifact

每个 test matrix job SHALL 以 `pytest --alluredir=<dir>` 收集 Allure 原始结果，并在 job 结束时 upload artifact，命名 SHALL 包含域标识（如 `allure-results-user`），保留期 SHALL ≥ 7 天。

#### Scenario: matrix job 上传 allure-results

- **WHEN** user 域 matrix job 完成 pytest
- **THEN** SHALL 存在可下载的 artifact 含 Allure JSON 结果
- **AND** artifact 名称 SHALL 可区分域（含 `user`）

### Requirement: Local domain test tasks

Taskfile SHALL 提供 `test:user`、`test:catalog`、`test:ordering`、`test:infra`、`test:unit` 任务，分别运行与 CI matrix 相同路径的 pytest；SHALL 加载 `APP_ENV_FILE=.env.test`。

#### Scenario: test:user 路径与 CI 一致

- **WHEN** 开发者执行 `devbox run -- task test:user`
- **THEN** SHALL 运行 `tests/user` 与 `tests/unit/user` 下 pytest

### Requirement: Local Allure report tasks

Taskfile SHALL 提供 `test:reports` 与 `latest:report`。`test:reports` SHALL 依赖数据库与 Redis 就绪（`db:up` + `redis:up`），运行全量或 CLI 传入路径的 pytest 并写入 `reports/allure-results/`，随后 generate HTML 至 `reports/allure-report/`。`latest:report` SHALL 打开 `reports/allure-report/`（须先存在）。

#### Scenario: test:reports 写入 reports 目录

- **WHEN** 开发者在 db/redis 就绪后执行 `devbox run -- task test:reports`
- **THEN** SHALL 创建或更新 `reports/allure-results/` 与 `reports/allure-report/`

#### Scenario: latest:report 无报告时失败

- **WHEN** 开发者未运行 `test:reports` 即执行 `latest:report`
- **THEN** task SHALL 以非零退出码失败并提示先运行 `test:reports`

#### Scenario: reports 不入库

- **WHEN** 查看 `.gitignore`
- **THEN** SHALL 忽略 `reports/` 目录
