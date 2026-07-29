## Why

当前 integration 测试的 fixture 与 helper 普遍返回 `dict[str, Any]`，字段通过 `**dict` 叠加与 `["json"]["id"]` 访问，调试与 IDE 补全体验差，且与业务域已定义的 Pydantic schema 重复维护。需要在不修改 `app/*/schemas.py` 的前提下，将测试数据与断言迁移到 typed 结构（Context + ActionResult + domain schema），为后续 TDD 迭代降低认知负担。

## What Changes

- 新增 `tests/support/`：`builders.py`（`build_*` 构造合法 domain schema）、`contexts.py`（fixture 用 Context dataclass）、各 helper 专用 Result dataclass（或同目录 `results.py`）
- 重构 `tests/conftest.py`：fixture 返回 Context（多步骤 fixture 使用嵌套 Context）；`register_user`、`login_user`、`create_category` 等 helper 返回 ActionResult 风格 dataclass；响应体通过 `XxxResponse.model_validate` 解析
- 迁移 `tests/user/`、`tests/catalog/` 下依赖 dict fixture 的 integration 测试：断言改为属性访问（如 `shop_owner.shop.id`）
- 4 条格式边界 HTTP 用例（密码长度、`category_ids` 空、primary 不在列表）**策略 B**：最小改动 + `TODO(test-schema-unit-tests)` 注释，留待下一 change 迁至 schema 单测并删除
- **BREAKING**（测试内部）：所有使用 `authenticated_user`、`shop_owner`、`register_user` 等返回 dict 的测试必须同步改写

## Non-goals

- 不修改 `app/user/schemas.py`、`app/catalog/schemas.py` 及任何业务 router/service/repository
- 不新增 schema 单元测试（`tests/*/test_schemas.py`）——留给后续 `test-schema-unit-tests` change
- 不删除上述 4 条格式边界 HTTP 用例（本 change 仅标记 TODO）
- 不引入泛型 `ActionResult[TRequest, TResponse]`、统一 HTTP 解析框架、fail-fast fixture 全面改造（`admin_auth_headers` 现有行为可保留）
- 不修改 `tests/infra/`、`tests/health/`（若不依赖 dict fixture）
- 不为每个 Field 新增 HTTP 422 smoke

## Capabilities

### New Capabilities

- `integration-test-typing`：integration 测试 support 层约定——domain schema 构造（builders）、Setup Context（fixture）、ActionResult（helper）；与业务 schema 的分层与命名纪律

### Modified Capabilities

<!-- 无：本 change 不改变对外 API 或业务需求，仅测试代码结构 -->

## Impact

- **业务域**：无运行时变更；测试触及 **user**、**catalog** 域 integration 用例
- **infra**：`tests/conftest.py`、`tests/support/`（新增）、`tests/user/*.py`、`tests/catalog/*.py`
- **API / 依赖**：无
- **后续 change**：`test-schema-unit-tests` 将承接格式边界测试迁移与 4 条 HTTP 用例删除
