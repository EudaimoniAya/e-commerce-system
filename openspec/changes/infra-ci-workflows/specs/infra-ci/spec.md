## ADDED Requirements

### Requirement: CI paths filter for test workflow

GitHub Actions test workflow（`test.yaml`）SHALL 使用 `dorny/paths-filter`（或等价）读取 `.github/utils/file-filters.yaml`，定义至少一个 `code` 过滤器，匹配业务代码与测试相关路径（含 `app/**`、`tests/**`、`alembic/**`、`pyproject.toml`、`uv.lock` 等）。`lint` 与 `test` job SHALL 仅在 PR/push 变更命中 `code` 时运行。

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
- **THEN** `test-failure-alert` job SHALL NOT 因 skip  alone 而 fail

### Requirement: CI test workflow naming

Validate 层 test workflow 文件 SHALL 命名为 `.github/workflows/test.yaml`，workflow `name` SHALL 为 `Run Tests`。

#### Scenario: workflow 文件与 display name

- **WHEN** 查看 `.github/workflows/test.yaml`
- **THEN** 首行 `name:` SHALL 为 `Run Tests`
- **AND** 旧文件 `ci.yml` SHALL NOT 存在

### Requirement: CI full test single job

GitHub Actions SHALL 提供单个 `test` job（**无** `strategy.matrix.domain`），声明 mysql + redis services、创建 `ecommerce_test`、执行 `alembic upgrade head`、设置与现 CI 一致的 env（含 `SMS_OTP_FIXED_CODE`），并运行**全量** pytest（等价 `task test` 或 `uv run pytest` 无路径子集）。

#### Scenario: 全量 pytest 无域子集

- **WHEN** `test` job 在命中 `code`  filter 后运行
- **THEN** SHALL 收集并执行 `tests/` 下全部用例（含 `tests/user`、`tests/catalog`、`tests/ordering`、`tests/infra`、`tests/ops`、`tests/unit`）
- **AND** SHALL NOT 按 domain 拆分多个 matrix job

## MODIFIED Requirements

### Requirement: CI lint job separation

GitHub Actions workflow SHALL 提供独立 `lint` job，执行 `task ruff` 与 `task check-test-imports`（或等价命令），**不** 声明 mysql/redis services。`lint` job SHALL 在 paths-filter 命中 `code` 时运行。

#### Scenario: lint job 无数据库依赖

- **WHEN** CI workflow 运行 `lint` job
- **THEN** job SHALL NOT 声明 `services.mysql` 或 `services.redis`
- **AND** SHALL 执行 ruff 与 test-import 检查

#### Scenario: lint 与 test 并行

- **WHEN** CI workflow 在 pull_request 或 push 到 dev/main 时触发且命中 `code`
- **THEN** `lint` job 与 `test` job SHALL 可并行启动（test 不 `needs: lint`）

### Requirement: CI Allure results artifact

test job SHALL 以 `pytest --alluredir=<dir>` 收集 Allure 原始结果，并在 job 结束时 upload artifact，命名 SHALL 为 `allure-results`（或等价单一名称，**不**要求域后缀），保留期 SHALL ≥ 7 天。

#### Scenario: test job 上传 allure-results

- **WHEN** test job 完成 pytest
- **THEN** SHALL 存在可下载的 artifact 含 Allure JSON 结果
- **AND** artifact 名称 SHALL 为 `allure-results` 或文档约定等价名

### Requirement: Local domain test tasks

Taskfile SHALL 提供 `test:user`、`test:catalog`、`test:ordering`、`test:infra`、`test:unit` 任务，分别运行对应路径的 pytest 供**本地加速**；SHALL 加载 `APP_ENV_FILE=.env.test`。CI **SHALL NOT** 要求与这些子命令路径一一对应的 matrix job。

#### Scenario: test:user 本地路径

- **WHEN** 开发者执行 `devbox run -- task test:user`
- **THEN** SHALL 运行 `tests/user` 与 `tests/unit/user` 下 pytest

## REMOVED Requirements

### Requirement: CI test domain matrix

**Reason**: 单体多域跨 service 耦合；全量单 job test 更简单且总 Actions 分钟更低；domain matrix 仅并行不减少测试范围。

**Migration**: CI 改用单 job 全量 pytest；本地仍可用 `task test:user` 等加速。

### Requirement: CI workflow_dispatch domain filter

**Reason**: 不再需要 CI 上按域手动筛选；全量 test 为默认；本地 Taskfile 子命令覆盖单域调试。

**Migration**: 移除 `workflow_dispatch` 的 `domain` input；保留 `workflow_dispatch` 可无输入触发全量 test（若实现）。
