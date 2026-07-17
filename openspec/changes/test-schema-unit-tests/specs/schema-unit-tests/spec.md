## ADDED Requirements

### Requirement: Schema unit tests live under tests/unit

Domain request schema 格式边界单元测试 SHALL 位于 `tests/unit/{domain}/test_{domain}_schema.py`。路径上每一级包目录 SHALL 包含 `__init__.py`（至少 `tests/unit/`、`tests/unit/user/`、`tests/unit/catalog/`）。

#### Scenario: user schema unit test file location

- **WHEN** 审查 user 域格式边界单测
- **THEN** SHALL 存在 `tests/unit/user/test_user_schema.py`

#### Scenario: catalog schema unit test file location

- **WHEN** 审查 catalog 域格式边界单测
- **THEN** SHALL 存在 `tests/unit/catalog/test_catalog_schema.py`

### Requirement: Invalid boundary tests use Pydantic construction

Schema 单元测试 SHALL 通过直接构造 `app/*/schemas.py` 中的 request 模型验证非法输入。非法输入 SHALL 使用 `pytest.raises(ValidationError)` 断言。测试 SHALL NOT 断言 error message、error loc 或 error type。

#### Scenario: invalid password raises ValidationError

- **WHEN** 测试构造 `RegisterRequest` 且 password 长度违反 `Field(min_length=8, max_length=32)`
- **THEN** 构造 SHALL 抛出 `ValidationError`

### Requirement: Parametrize homomorphic invalid inputs

同构非法输入（同一字段、同一断言模式）SHALL 使用 `@pytest.mark.parametrize`，且每个参数 SHALL 使用 `pytest.param(..., id="...")` 以保证失败报告可读。

#### Scenario: password cases use parametrize ids

- **WHEN** 运行 user schema 单测且某非法 password 用例失败
- **THEN** pytest 报告 SHALL 包含可读的 parametrize `id`（如 `too_short_7`）

### Requirement: RegisterRequest and LoginRequest share password cases

`RegisterRequest` 与 `LoginRequest` SHALL 共用同一非法 password 参数表（模块级常量）。两者 SHALL 各有一个 parametrize 测试函数覆盖该表。

#### Scenario: both auth request schemas reject short password

- **WHEN** 对 `RegisterRequest` 与 `LoginRequest` 分别传入同一非法短 password
- **THEN** 两者 SHALL 均抛出 `ValidationError`

### Requirement: Unit tests only cover invalid boundaries for MVP

本 change MVP SHALL 仅覆盖下列非法边界（对应原 integration TODO）：

- `RegisterRequest` / `LoginRequest`：password 过短、过长
- `ProductCreate`：`category_ids` 为空列表
- `ProductCreate`：`primary_category_id` 不在 `category_ids` 中

合法 min/max 边界 SHALL 由 integration 测试覆盖，本 change SHALL NOT 在 unit 中断言合法构造成功。

#### Scenario: empty category_ids rejected

- **WHEN** 测试构造 `ProductCreate` 且 `category_ids=[]`
- **THEN** 构造 SHALL 抛出 `ValidationError`

#### Scenario: primary not in category_ids rejected

- **WHEN** 测试构造 `ProductCreate` 且 `primary_category_id` 与 `category_ids` 中元素无交集（均为合法 UUID 字符串）
- **THEN** 构造 SHALL 抛出 `ValidationError`

### Requirement: Unit tests do not use integration support

Schema 单元测试 SHALL NOT import `tests.support` 或 `tests.conftest` 的 fixture/helper。SHALL NOT 使用 `@pytest.mark.integration` 或 request `client` / `db_session` fixture。

#### Scenario: schema unit test imports are limited

- **WHEN** 审查 `tests/unit/**/test_*_schema.py` 的 import
- **THEN** SHALL 仅依赖 `app.*.schemas` 与测试/标准库（如 `pytest`、`uuid`、`Decimal`）
- **AND** SHALL NOT 出现 `from tests.support` 或 `from tests.conftest`
