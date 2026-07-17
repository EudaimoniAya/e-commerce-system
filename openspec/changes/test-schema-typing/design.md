## Context

当前 `tests/conftest.py` 与 catalog/user integration 测试使用 `dict[str, Any]` 作为 fixture 与 helper 返回值，通过 `**registered` 叠加字段、`result["json"]["id"]` 访问响应。业务域已在 `app/user/schemas.py`、`app/catalog/schemas.py` 定义请求/响应 Pydantic schema，与 router `response_model` 一致，但测试层未复用。

格式/字段级校验已在 domain schema（Pydantic）中实现；service 层负责业务规则（重复资源、权限、状态机）。格式边界 HTTP 用例将留给后续 `test-schema-unit-tests` change。

约束：测试代码可 import 各域 `schemas`，但不得修改 `app/` 下业务 schema；integration 测试继续 `@pytest.mark.asyncio` + httpx `AsyncClient`（见 `.cursor/rules/async-integration-testing.mdc`）。

## Goals / Non-Goals

**Goals:**

- 用 **domain schema** 替代 dict 构造请求与解析合法响应
- 用 **Context**（`@dataclass`）作为 Setup fixture 返回类型；多步骤 fixture 使用嵌套 Context（如 `ShopOwnerContext.auth`）
- 用 **ActionResult**（每 helper 一个 `@dataclass`，无泛型）作为可复用 HTTP helper 返回类型；组合内 `body: XxxResponse | None`
- 迁移 user/catalog integration 测试断言为属性访问
- 4 条格式边界 HTTP 用例策略 B：最小改动 + TODO 注释

**Non-Goals:**

- 泛型 `ActionResult[TRequest, TResponse]`、统一 `parse_action_result` 框架
- 全面 fail-fast fixture 改造（保留 `admin_auth_headers` 现有 `pytest.fail` 即可）
- schema 单元测试、删除格式 HTTP 用例
- 修改 `tests/infra/`、`tests/health/`（无 dict fixture 依赖时）

## Decisions

### 1. 三层类型分工

| 层次 | 位置 | 用途 |
|------|------|------|
| domain schema | `app/*/schemas.py` | API 契约；factory `build_*` 与 `model_validate` 复用 |
| Context | `tests/support/contexts.py` | fixture 返回值；组合 schema + `headers` + `status_code` |
| ActionResult | `tests/support/results.py` 或 conftest 旁 | helper 返回值；`status_code` + `body \| None` + 必要上下文字段 |

**Rationale:** 避免污染 domain schema，同时让测试具备 IDE 补全。Context 与 ActionResult 不叫 schema，仅 **包含** domain schema 字段。

### 2. Context 字段约定

- 每层 Context **自有** `status_code`（不混用步骤）
- `ShopOwnerContext.status_code` 表示 **开店（POST /shops）** 一步；注册状态在 `auth.status_code`
- 成功路径 Setup：`shop`、`token` 等非 None；本 change **不强制** fail-fast，可与现行为一致（`admin_auth_headers` 除外）
- 嵌套：`ShopOwnerContext` 含 `auth: AuthContext`

**Alternatives considered:** 扁平 Context 重复字段 — 否决，多步骤 fixture 可读性差。

### 3. ActionResult：每 helper 独立 dataclass（无泛型）

示例：

```python
@dataclass
class RegisterResult:
    status_code: int
    body: TokenResponse | None
    email: str
    password: str
```

`login_user` → `LoginResult`；`create_category` → `CategoryResult`；必要时 `create_shop` → `ShopResult`。

**Alternatives considered:** 泛型基类 — 否决，降低首版认知负担。

解析规则（helper 内）：

- `2xx`：`body = TokenResponse.model_validate(response.json())`（失败则测试报错）
- 非 `2xx`：`body = None`；需要断言 `detail` 时保留 `response.json()` 到可选字段或局部变量（首版可不统一 `raw_json`）

### 4. builders：`build_*` 函数式工厂

- `build_register_request`、`build_shop_create`、`build_product_create` 等
- 返回合法 domain schema；构造时 Pydantic 校验
- 模块 `tests/support/builders.py`；`build_*` 前缀（非链式 Builder 类）
- 替代 `create_shop_payload`、`product_payload` fixture

### 5. 格式边界 HTTP 用例（策略 B）

保留以下 4 条，仅加 `# TODO(test-schema-unit-tests): 迁至 schema 单测后删除`：

- `test_register_password_too_short_returns_422`
- `test_register_password_too_long_returns_422`
- `test_create_product_empty_category_ids_returns_422`
- `test_create_product_invalid_primary_category_returns_422`

继续 raw dict 或现有 helper 参数绕过合法 `build_*`；不扩写 typed 属性断言。

### 6. 测试迁移范围

- **In scope:** `tests/conftest.py`、`tests/user/*.py`、`tests/catalog/*.py`
- **Out of scope:** `tests/infra/`、`tests/health/`（除非 import 已删除的 dict 符号）

## Risks / Trade-offs

- **[Risk] 大 PR _touch 多文件** → 按 support → conftest → user → catalog 顺序提交；每步 `task ci`
- **[Risk] 4 条格式测重复维护** → TODO 标记 + 下一 change 删除
- **[Risk] Result 类型 proliferation** → 仅对已存在 helper 定义 Result；GET 端点首版可 inline `model_validate`
- **[Trade-off] 无 fail-fast** → 失败 fixture 仍可能带 `body=None`；与现 dict 行为一致，后续可加

## Migration Plan

1. 新增 `tests/support/{builders,contexts,results}.py`
2. 重构 `conftest.py` helpers/fixtures
3. 逐目录改测试断言
4. 标记 4 条格式 TODO
5. `devbox run -- task ci` 全绿

Rollback：revert 单 commit/分支；无 DB migration、无 API 变更。

## Open Questions

- （无阻塞项）后续 change 是否引入统一 `raw_json` 字段 — 本 change 按需在单测内局部处理 `detail`
