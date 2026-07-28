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
