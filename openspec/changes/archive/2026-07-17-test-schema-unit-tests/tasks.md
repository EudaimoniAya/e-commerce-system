## 1. tests/unit 目录与 user schema 单测

- [x] 1.1 新增 `tests/unit/__init__.py`、`tests/unit/user/__init__.py`
- [x] 1.2 新增 `tests/unit/user/test_user_schema.py`：模块级非法 password 参数表；`RegisterRequest` 与 `LoginRequest` 各一个 `@pytest.mark.parametrize` 测试；仅 `pytest.raises(ValidationError)`

## 2. catalog schema 单测

- [x] 2.1 新增 `tests/unit/catalog/__init__.py`、`tests/unit/catalog/test_catalog_schema.py`：`_valid_product_create_kwargs` helper
- [x] 2.2 parametrize 覆盖 `category_ids=[]` 与 primary ∉ category_ids（合法 UUID 字符串）；仅断言 `ValidationError`

## 3. 删除冗余 integration 格式用例

- [x] 3.1 从 `tests/user/test_register.py` **整函数删除** `test_register_password_too_short_returns_422`、`test_register_password_too_long_returns_422`（不得半留 HTTP 格式断言）
- [x] 3.2 从 `tests/catalog/test_create_product.py` **整函数删除** `test_create_product_empty_category_ids_returns_422`、`test_create_product_invalid_primary_category_returns_422`

## 4. 验证与 DoD

- [x] 4.1 grep 确认无残留 `TODO(test-schema-unit-tests)`；`tests/unit/**` 无 `tests.support` / `client` fixture 依赖
- [x] 4.2 运行 `devbox run -- task db:up`、`devbox run -- task migrate`、`devbox run -- task ci` 全绿

> **Apply 约定**：建议顺序 §1 → §2 → §3 → §4；每完成一节可运行 `devbox run -- task test` 验证。
>
> **已前置完成**：杂项 Context fixture 参数类型注解（commit `b3c3834`）。
>
> **Archive 时**：同步 `schema-unit-tests` 主 spec；更新 `integration-test-typing` 主 spec（移除 deferred、合并 ADDED/REMOVED delta）。
