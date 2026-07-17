## Why

`test-schema-typing` 将 4 条格式边界校验暂留为 integration HTTP 422 用例（带 `TODO(test-schema-unit-tests)`）。格式/字段约束已在 `app/*/schemas.py` 的 Pydantic 模型中实现，通过 HTTP 重复断言成本高、与 integration 业务路径耦合，且不适合 parametrize。现将这些校验下沉为 schema 单元测试，并删除冗余 integration 用例，减轻维护负担。

## What Changes

- 新增 `tests/unit/` 目录结构（含各层 `__init__.py`）：`tests/unit/user/test_user_schema.py`、`tests/unit/catalog/test_catalog_schema.py`
- 以 **纯 Pydantic 构造/校验** + `@pytest.mark.parametrize` 覆盖 4 条 TODO 对应非法边界（仅断言 `ValidationError`，不断言 error message）
- `RegisterRequest` 与 `LoginRequest` 共用同一非法 password 参数表
- **删除** 4 条 integration 格式 HTTP 用例（整函数删除，不得半留 HTTP 格式断言）
- 更新 `integration-test-typing` 主 spec：格式边界归属 `tests/unit/`，integration 不得重复
- **杂项（已提交）**：catalog/user integration 测试中 Context fixture 参数补全类型注解（`AuthContext`、`ShopOwnerContext`、`AdminAuthContext`）

## Non-goals

- 不修改 `app/user/schemas.py`、`app/catalog/schemas.py` 及任何业务 router/service/repository
- 不新增完整测试架构 spec（`test-architecture` / `test-layering` 留待后续 change）
- 不拆分 conftest、不 lazy import app；不新增 `task test:unit`、不拆 CI job
- MVP 不 parametrize UUID 格式非法输入（业务路径与 builders 均使用合法 UUID；malformed 输入留待后续）
- 不 parametrize EmailStr 等其他 Field 边界；不 sweep `ProductUpdate` 等未在 TODO 中的 schema
- 不在 unit 测合法 min/max 边界（合法路径由 integration 覆盖）
- 不迁移 `tests/infra/test_auth.py`；不调整 health/readiness 运维探针目录

## Capabilities

### New Capabilities

- `schema-unit-tests`：domain request schema 格式边界单元测试约定——目录、`test_{domain}_schema.py` 命名、parametrize 非法输入、与 integration 的分工

### Modified Capabilities

- `integration-test-typing`：移除「Format boundary HTTP tests deferred」；明确格式边界在 `tests/unit/`，integration SHALL NOT 重复同类 HTTP 422 格式用例

## Impact

- **业务域**：无运行时变更；测试触及 **user**、**catalog** 域 schema 与 integration 用例
- **测试**：新增 `tests/unit/`；修改 `tests/user/test_register.py`、`tests/catalog/test_create_product.py`；更新 `openspec/specs/integration-test-typing/spec.md`（apply/archive 时同步）
- **API / 依赖**：无
