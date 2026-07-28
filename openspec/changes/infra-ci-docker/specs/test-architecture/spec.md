# test-architecture

## ADDED Requirements

### Requirement: Allure report hierarchy on test cases

集成测试与 schema 单元测试 Case SHALL 使用 `allure-pytest` 装饰器标注报告层级：`@allure.epic` 表示业务域或测试类别（`user`、`catalog`、`ordering`、`infra`、`ops`、`unit`）；`@allure.feature` 表示场景模块（SHALL 与 `test_*.py` 文件主题对齐，如 `sms_register`、`create_product`）；`@allure.title` 提供 Story 级中文可读标题（SHALL 从现有 docstring 或测试意图迁移，与 BDD 场景描述一致）。

#### Scenario: user 域用例含 epic 与 feature

- **WHEN** 审查 `tests/user/test_sms_register.py` 中任一 `@pytest.mark.integration` 用例
- **THEN** SHALL 存在 `@allure.epic("user")` 与 `@allure.feature(...)` 装饰器
- **AND** SHALL 存在 `@allure.title(...)` 非空字符串

#### Scenario: catalog 域用例 epic 为 catalog

- **WHEN** 审查 `tests/catalog/test_create_product.py` 中 integration 用例
- **THEN** `@allure.epic` 值 SHALL 为 `catalog`

#### Scenario: ops 探针用例 epic 为 ops

- **WHEN** 审查 `tests/ops/test_readiness.py` 中用例
- **THEN** `@allure.epic` 值 SHALL 为 `ops`

#### Scenario: unit 用例 epic 为 unit

- **WHEN** 审查 `tests/unit/user/test_phone.py` 中用例
- **THEN** `@allure.epic` 值 SHALL 为 `unit`

### Requirement: Allure pytest dependency

项目 dev 依赖 SHALL 包含 `allure-pytest`。pytest 运行时可接受 `--alluredir=<path>` 参数输出 Allure 原始结果。

#### Scenario: dev 依赖可导入 allure

- **WHEN** 执行 `uv sync` 后运行 `uv run python -c "import allure"`
- **THEN** SHALL 成功无 ImportError

### Requirement: Local report output discipline

Allure 原始结果与 generate 后的 HTML SHALL 写入项目根下 `reports/` 目录（`reports/allure-results/`、`reports/allure-report/`）；该目录 SHALL 被 gitignore，**SHALL NOT** 提交至版本库。

#### Scenario: reports 目录 gitignore

- **WHEN** 运行 `git check-ignore -v reports/allure-results`
- **THEN** SHALL 匹配 `.gitignore` 规则

### Requirement: No redundant curl smoke scripts in scripts/

项目 **SHALL NOT** 在 `scripts/` 下新增与 pytest integration 重复的 `*_curl_smoke.sh` 或等价 bash HTTP 编排脚本。业务 API 主流程与回归 SHALL 由 `tests/{domain}/` integration Case + `tests/support/helper/` 覆盖，并经 `task ci` / 域测试任务在 CI 与本地执行。

README MAY 保留零散的 curl 示例供手动调试，但 **SHALL NOT** 维护「一键烟雾」类 shell 脚本作为第二套自动化测试。

#### Scenario: apply 本地验证不依赖 curl 烟雾脚本

- **WHEN** OpenSpec change 的 tasks 描述本地验证或 DoD
- **THEN** SHALL 以 `devbox run -- task migrate` + `devbox run -- task ci`（或域 `task test:*`）为验收标准
- **AND** SHALL NOT 要求新增或运行 `scripts/*_curl_smoke.sh`

#### Scenario: scripts 目录无 curl 烟雾脚本

- **WHEN** 列出 `scripts/` 目录
- **THEN** SHALL NOT 存在 `*_curl_smoke.sh` 文件
