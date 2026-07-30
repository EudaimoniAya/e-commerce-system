# 开发工作流

**OpenSpec 5 步**：`explore` → `propose` → `apply` → `archive` → `sync`

- **propose** 产出 4 个产物：`task.md`、`design.md`、`proposal.md`、`spec.md`。SDD 规格 + BDD 场景在此定稿（落在 `spec.md`）。
- **apply** 严格遵守 **SDD + BDD + TDD**：一开始就照接口的 BDD 场景写测试用例，然后跑**红-绿-重构**循环，**绝不 code-first**。
- **archive / sync**：收尾。

**其他约束**
- Git 采用 **gitflow** 工作流。
- 分支前缀：`docs/*` 用于 ADR、架构文档等**无行为变更**的提交；`feature/*` 用于 OpenSpec 垂直切片、**可演示功能**交付。
- 平均每 **4–6 个 feature** 做一次架构诊断 + 代码重构。

# 默认行为

1. **不擅自做架构决策** —— 遇到架构级选择，给出方案+权衡，交用户定夺。
2. **apply 阶段严格 test-first** —— 从 BDD 场景推导测试，红绿重构，不跳步直接写实现。
3. **尊重 propose 产物边界** —— spec/场景定稿后以其为准，不擅自改规格。
4. 涉及重构或评审时，**顺带讲清原理**，不只给结果。

---

# 从 .cursor 规则继承的工程纪律

> 以下规则来源于 `.cursor/rules/`，转化为 Claude Code 可直接遵循的指令。

## 1. 数据库/迁移/测试命令必须用 `devbox run --` 包装

本项目依赖 devbox 提供 `task`、`mysqladmin`、`mysql`、`mysqld`。在裸 WSL/bash 中直接执行会导致 `command not found`。

**禁止裸 shell 执行**（会失败）：
```bash
task db:up
task migrate
task test
task ci
```

**必须用 `devbox run --` 包装**：
```bash
devbox run -- task db:up
devbox run -- task migrate
devbox run -- task ci
devbox run -- task test
```

**执行顺序（本地验证）**：
1. `devbox run -- task db:up`（含 mysqladmin ping 轮询）
2. `devbox run -- task migrate`
3. `devbox run -- task ci` 或 `devbox run -- task test`

**例外**：纯静态检查（`uv run ruff check .`）可不用包裹；MySQL 已确认就绪后，仅 Python 连库操作可 `uv run alembic current`。

> 来源：`.cursor/rules/devbox-run-for-db-ops.mdc`

## 2. 跨域 import 纪律

本项目是**单体多域（Modular Monolith）**架构。域间协作只走**公开 service 接口 + schema（DTO）**，禁止穿透到对方持久化层。

**禁止**：
```python
from catalog.models import Product              # ✗ 跨域 import 对方 ORM
from catalog.repository import ProductRepository # ✗ 跨域 import 对方 repository
from app.ai.tools import recommend               # ✗ 业务域 import ai
```

**允许**：
```python
from catalog.schemas import ProductSummary   # ✓ 跨域 schema
from catalog.service import get_product      # ✓ 跨域 service
from ordering.repository import OrderRepository  # ✓ 域内 repository
from ordering.models import Order                # ✓ 域内 model
from app.infra.database import get_db, Base      # ✓ 各域 → infra
```

**细则**：
- 写操作跨域：必须调目标域 **service**，不得直接写对方表/ORM
- SQLAlchemy relationship：域内可用，跨域只存 FK 字段
- AI Tool：只调各域 service，不直连数据库
- infra：不 import 任何业务域模块
- 测试 mock 跨域：mock **service** 或 HTTP 层，不 mock 对方 ORM

> 来源：`.cursor/rules/cross-domain-imports.mdc`

## 3. 异步集成测试必须用 AsyncClient

**核心原则**：异步代码必须用异步方式测试。

**禁止**：
```python
from fastapi.testclient import TestClient

def test_register(client: TestClient):                        # ✗
    client.post("/auth/register", json={...})
```

**必须**：
```python
import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_register(client: AsyncClient):                 # ✓
    response = await client.post("/auth/register", json={...})
    assert response.status_code == 201
```

`tests/conftest.py` 已提供 async `client` fixture；`TestClient` 会在后台线程另开 event loop，与 pytest-asyncio/全局 AsyncEngine 冲突，报 `Future attached to a different loop`。

| 场景 | 做法 |
|------|------|
| HTTP + DB / Redis | `@pytest.mark.asyncio` + `await client.*` |
| 纯 JWT / 纯函数 | 直接测模块函数，不必启 client |
| 探针 | 仍统一 AsyncClient |
| 独立 DB 探测 | service 内独立 `create_async_engine` |

> 来源：`.cursor/rules/async-integration-testing.mdc`
