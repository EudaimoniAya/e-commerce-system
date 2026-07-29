## Context

`test-schema-typing` 已在 integration 层完成 Context/Result/builders 重构，4 条格式边界 HTTP 用例以 TODO 标记待迁。Pydantic 约束定义在 `app/user/schemas.py`（`RegisterRequest`、`LoginRequest` 的 password `Field`）与 `app/catalog/schemas.py`（`ProductCreate` 的 `category_ids`、`primary_category_id`）。

项目体量小，采用 **简单分层**：保留合并的 `tests/conftest.py`（collection 时可 import app），以 **目录 + 测试体纪律** 区分 unit 与 integration；完整测试架构规范留待后续 `test-architecture` change。

## Goals / Non-Goals

**Goals:**

- 在 `tests/unit/{domain}/test_{domain}_schema.py` 用 sync 单测 + parametrize 覆盖 4 条 TODO 非法边界
- `RegisterRequest` 与 `LoginRequest` 复用同一非法 password 参数表
- 删除对应 integration HTTP 用例，避免重复
- 各 `tests/unit/` 包含 `__init__.py`

**Non-Goals:**

- conftest 拆分、ops 探针目录、auth 搬迁、`task test:unit`
- UUID 格式、EmailStr、合法 min/max 边界、ProductUpdate sweep
- 断言 error message / ValidationError loc

## Decisions

### 1. 目录与命名

```
tests/unit/
├── __init__.py
├── user/
│   ├── __init__.py
│   └── test_user_schema.py
└── catalog/
    ├── __init__.py
    └── test_catalog_schema.py
```

**Rationale:** 与 `app/{domain}/` 镜像；文件名 `test_{domain}_schema.py` 允许扩展，不必强制 `test_schemas.py`。

### 2. 单测模式：仅非法边界 + parametrize

- 构造非法 kwargs → `pytest.raises(ValidationError)`
- 模块级 `_INVALID_PASSWORDS` 等常量 + `pytest.param(..., id="...")`
- catalog 用文件内 `_valid_product_create_kwargs(**overrides)` 提供合法 baseline 再 override 非法字段

**Alternatives considered:** 合法边界 parametrize — 否决，integration 已覆盖 happy path。

### 3. 与 integration 分工

| 类型 | 位置 | 示例 |
|------|------|------|
| Schema 格式非法 | `tests/unit/` | password too short |
| 业务规则 422 | integration | 重复邮箱、closed shop |

删除 integration 用例时 **整函数移除**，不在原文件保留仅 `assert status_code == 422` 的格式断言。

### 4. conftest 与 import 纪律

- 不修改根 `tests/conftest.py` 结构
- unit 测试体 **SHALL NOT** request `client` / `db_session`；**SHALL NOT** import `tests.support`
- 仅 import `app.*.schemas`、`pytest`、`ValidationError`（及 catalog 单测所需的 `uuid`、`Decimal` 等构造辅助）

**Note:** pytest 收集 `tests/unit/` 时仍会执行根 conftest 模块级 import app；小项目可接受。

### 5. MVP 覆盖范围

**User（`test_user_schema.py`）:**

- password too short / too long → `RegisterRequest` + `LoginRequest`（共享参数表）

**Catalog（`test_catalog_schema.py`）:**

- `ProductCreate(category_ids=[])` → ValidationError
- `ProductCreate` primary ∉ category_ids（两个合法 UUID 字符串）

**不覆盖:** malformed UUID 字符串（Non-goal；内部业务与 builders 不产生此类输入）

## Risks / Trade-offs

- **[Risk] 根 conftest import app 使 unit 非「纯隔离」** → 小项目可接受；后续 architecture change 可 lazy import
- **[Risk] ProductCreate 校验顺序差异** → 单测只断言 ValidationError，不断言错误类型/顺序
- **[Trade-off] 无独立 CI unit job** → 全量 `task ci` 仍须 MySQL；unit 用例轻量，增量成本可忽略

## Migration Plan

1. 新增 `tests/unit/` 与 schema 单测
2. 删除 4 个 integration 测试函数
3. `devbox run -- task ci` 全绿
4. archive 时同步 `integration-test-typing` 与新增 `schema-unit-tests` 主 spec

Rollback：revert 分支；无 API/DB 变更。

## Open Questions

- （无阻塞项）完整 test-layering spec 留待 `test-architecture` change
