## Context

前两轮测试重构已交付：

- **test-schema-typing**：`tests/support/{builders,contexts,results}.py`；单步 `*Result`；胖 Context（含 `ShopOwnerContext.auth` 嵌套）；helper 在 `tests/conftest.py`
- **test-schema-unit-tests**：`tests/unit/{domain}/test_{domain}_schema.py`；integration 不重复格式 422

当前痛点（见 `docs/troubleshooting/测试架构-旧模式反模式记录.md`）：

- `tests/catalog/test_create_product.py` 内 `_create_product` 被 3 个 test 文件 cross-import
- `register_and_open_shop` 返回 `ShopOwnerContext`（helper 返 Context，数据流倒置）
- Context 存储型 `headers` 与嵌套 `auth` 易 stale、字段膨胀
- 大量 Case 参数裸 `client`；fixture 未统一 fail-fast（`shop_owner` 可透传失败状态）

约束：integration 继续 `@pytest.mark.asyncio` + httpx `AsyncClient`；unit 不 import support；不修改 `app/`。

## Goals / Non-Goals

**Goals:**

- 明确四层测试架构并写入全局 spec + Cursor rule
- 引入 `PipelineResult` 作为唯一组合容器；`step(Type)` / `all(Type)` 精确类型匹配
- helper 只返 `*Result` / `PipelineResult`；Context 仅 fixture 注入且 `root: PipelineResult`；fail-fast Setup
- 迁移 user/catalog 测试：零 test 内 helper、零 test 互 import；场景断言不变；`devbox run -- task ci` 全绿
- 记录旧架构签名至 troubleshooting 文档

**Non-Goals:**

- 见 proposal Non-goals
- 不在本 change 实现通用 ActionTree

## Decisions

### 1. 四层职责

| 层 | 位置 | 职责 |
|----|------|------|
| Case | `tests/**/test_*.py` | Assert-First；Act 可见；禁止 helper/seed/test 互 import |
| Fixture | `conftest.py` | 生命周期 + 注入 `*Context`；fail-fast |
| Support | `tests/support/` | helper、builders、results、contexts、PipelineResult |
| Utilities | support 内纯函数 | `bearer_headers` 等投影，无 I/O |

### 2. PipelineResult API

```python
@dataclass(frozen=True)
class PipelineResult:
    steps: tuple[ActionResult, ...]

    def step(self, result_type: type[T]) -> T:
        matches = self.all(result_type)
        if len(matches) != 1:
            raise LookupError(result_type)
        return matches[0]

    def all(self, result_type: type[T]) -> tuple[T, ...]:
        return tuple(
            item for item in self.steps if type(item) is result_type
        )
```

- **精确匹配** `type(item) is result_type`，不用 `isinstance`（防未来基类误判）
- 未找到或多于一个（`step` 语义）→ `LookupError`
- MVP：同 Pipeline 内每种 Result 类型至多一次；多次用 `all(Type)[i]`

**Alternatives considered:** 递归 ActionTree + 字符串查询 — 否决；ad-hoc `OpenShopResult(register=, shop=)` — 否决。

### 3. Context 极薄化

```python
@dataclass(frozen=True)
class ShopOwnerContext:
    root: PipelineResult
```

- **MUST NOT** 存储型 `headers` / `email` 拷贝
- **MAY** 只读 `@property` 作投影；**默认** Case 使用 `bearer_headers(pipeline.step(RegisterResult))`
- 废弃为主模型：`ShopOwnerContext.auth: AuthContext` 嵌套

### 4. Orchestrator 与返回值

| 类型 | 返回值 |
|------|--------|
| 原子 helper（一次 HTTP） | `*Result` |
| 线性 orchestrator | `PipelineResult` |
| 扇入 orchestrator（一步新 HTTP） | `*Result` |
| 扇入 orchestrator（多步 Arrange） | `PipelineResult`（仅新 steps） |

- 扇入 **MUST NOT** 成为 Case 内前置数据的唯一来源（禁止 one-shot 黑盒）
- 前置 **MUST** 保留在 fixture `Context.root`、显式参数、Arrange 变量
- **Act 的 `*Result` MUST NOT** 进入 Setup Context

### 5. Arrange / Act 铁律

- **被测 API 以外皆为 Arrange**（含 fixture 内 `register_and_open_shop`）
- Setup fixture **MUST NOT** 执行被测 Act（如测 `create_product` 时 fixture 不得调用 `create_product`）
- 失败场景：**Case 内** await 原子 helper + assert；**不用**失败 Context fixture

### 6. helper 不 assert 成功

- 原子 helper 如实返回 `status_code`；Case 或 fixture 边界断言
- 移除 `_create_product` 内 `assert response.status_code == 201` 模式

### 7. 目录

- `tests/ops/`：`test_health.py`、`test_readiness.py`、`test_migration_smoke.py`（自 health/infra 迁入）
- `tests/infra/`：保留 `test_auth.py`、`test_database.py` 等非探针
- `tests/support/actions.py`：HTTP helper / orchestrator（自 conftest 迁出）

### 8. Enforcement

- ruff ANN on `tests/`
- CI grep：禁止 `from tests.<domain>.test_` 互 import

### 9. 旧架构文档

- `docs/troubleshooting/测试架构-旧模式反模式记录.md` 在 refactor **前** 记录签名（change 开头 Task 0 完成），供 code review 对照

## Risks / Trade-offs

- **[Risk] 大面积 touch 测试文件** → 按 support → conftest → catalog → user → ops 顺序；每步 `task ci`
- **[Risk] Context 字段路径变更** → troubleshooting 文档 + 类型注解辅助 IDE 跳转
- **[Risk] `step(ShopResult)` 学习成本** → Cursor rule + 示例 Case；比 ad-hoc 字段名长期更可维护
- **[Trade-off] conftest 仍 import app** → 与 schema-unit-tests 一致，本 change 不 lazy import

## Migration Plan

1. 撰写旧架构 troubleshooting 文档（签名快照）
2. 新增 `PipelineResult`、`ProductResult`、`actions.py`、`seeds.py`、`bearer_headers`
3. 重构 orchestrator：`register_and_open_shop` → `PipelineResult`；新增 `create_product`
4. 重构 fixture：fail-fast + `*Context(root=...)`
5. 迁移 catalog/user tests；删除 test 内 helper 与 cross-import
6. 迁 ops 目录；补类型注解
7. ruff ANN + CI grep；Cursor rule
8. `devbox run -- task ci` 全绿
9. archive 时 sync 主 spec

Rollback：revert 分支；无 API/DB 变更。

## Open Questions

- （无阻塞项）是否在 `ShopOwnerContext` 保留可选 `@property headers` — 默认否，仅用 `bearer_headers()`
