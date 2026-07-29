## REMOVED Requirements

### Requirement: Format boundary HTTP tests deferred

**Reason**: 格式边界已迁移至 `tests/unit/{domain}/test_{domain}_schema.py`（`schema-unit-tests` capability）；integration 层不再保留对应 HTTP 422 格式用例。

**Migration**: 删除下列 integration 测试函数；格式校验改由 schema 单元测试覆盖：

- `test_register_password_too_short_returns_422`
- `test_register_password_too_long_returns_422`
- `test_create_product_empty_category_ids_returns_422`
- `test_create_product_invalid_primary_category_returns_422`

## ADDED Requirements

### Requirement: Format boundaries belong to schema unit tests

DTO 格式/字段级非法输入（如 password 长度、`ProductCreate` 空 `category_ids`、primary 不在列表）SHALL 在 `tests/unit/{domain}/test_{domain}_schema.py` 中测试。Integration 测试 SHALL NOT 重复上述格式的 HTTP 422 用例。Integration 仍 SHALL 覆盖业务规则导致的 422（如重复邮箱、closed shop 下创建商品）。

#### Scenario: no duplicate password length HTTP test in integration

- **WHEN** 实现本 change 后审查 `tests/user/test_register.py`
- **THEN** SHALL NOT 存在仅断言 password 长度导致 HTTP 422 的 integration 用例
- **AND** 对应校验 SHALL 存在于 `tests/unit/user/test_user_schema.py`

#### Scenario: no duplicate product category format HTTP test in integration

- **WHEN** 实现本 change 后审查 `tests/catalog/test_create_product.py`
- **THEN** SHALL NOT 存在仅断言 `category_ids` 格式/组合导致 HTTP 422 的 integration 用例（空列表、primary 不在列表）
- **AND** 对应校验 SHALL 存在于 `tests/unit/catalog/test_catalog_schema.py`
