# 集成测试：httpx.AsyncClient 与 Event Loop 线程冲突

> **性质**：个人学习笔记（不进 OpenSpec spec 正文）；与 `user-auth` change 相关，记录为何弃用 Starlette `TestClient`、统一采用 `httpx.AsyncClient + ASGITransport`。

- **状态**：已采纳（本项目实践）
- **日期**：2026-07-13
- **背景**：user 域实现后，部分 integration 测试失败，报错 `RuntimeError: Task ... got Future <Future pending> attached to a different loop`，并伴随 `readexactly() called while another coroutine is already waiting`、`SAWarning: non-checked-in connection`、`Event loop is closed`。根因是 **async 全局 Engine 单例** 与 **TestClient 的 AnyIO BlockingPortal 双事件循环** 冲突，而非业务逻辑错误。

## 决策

**集成测试 HTTP 层统一使用 `httpx.AsyncClient` + `ASGITransport(app=app)`，不再使用 Starlette/FastAPI 的同步 `TestClient`。**

配套措施（已实现）：

1. `tests/conftest.py` 提供 async `client` fixture，与 `pytest-asyncio` 共用同一事件循环。
2. 凡 `@pytest.mark.integration` 测试前后调用 `reset_engine()`，避免连接池跨 loop 残留。
3. `test_get_db_select_one` 使用独立 `create_async_engine`，不初始化全局 `_engine` 单例。

## 问题现象

| 类型 | 典型报错 |
|------|----------|
| 主错误 | `RuntimeError: ... got Future attached to a different loop` |
| 连锁 | `readexactly() called while another coroutine is already waiting for incoming data` |
| 清理 | `SAWarning: garbage collector is trying to clean up non-checked-in connection` |
| 收尾 | `RuntimeError: Event loop is closed` |

失败集中在需 **TestClient → FastAPI → `Depends(get_db)` → 全局 `_engine`** 的用例；纯 Pydantic 422、JWT 单元测试、readiness（独立 engine）仍可通过。

## 架构背景

### TestClient 如何工作（不启 HTTP 服务器）

`TestClient` 不走 TCP，直接调用 ASGI 三元组：

```text
client.post("/auth/register")
  → 构造 HTTP 请求
  → ASGITransport 转为 scope / receive / send
  → await app(scope, receive, send)
```

但测试函数通常是 **同步** `def test_...()`，主测试线程 **没有 running event loop**，无法直接 `await` async 路由。

### AnyIO BlockingPortal：sync ↔ async 桥

Starlette `TestClient` 内部使用 **AnyIO BlockingPortal**：

```text
┌─────────────────────────┐      BlockingPortal      ┌──────────────────────────────┐
│ 主测试线程（同步）         │  ─────────────────────►  │ Portal 后台线程               │
│ 无 running loop          │   提交 coroutine 并阻塞等待  │ 有独立 asyncio event loop     │
│ client.post() 阻塞       │  ◄─────────────────────  │ await app(...) / await DB    │
└─────────────────────────┘                          └──────────────────────────────┘
```

- **Portal 线程内**通常只有一个 loop（符合「每线程一个 loop」惯例）。
- **进程内**同时存在：pytest-asyncio 的 loop（跑 `@pytest.mark.asyncio` 测试）与 Portal 的 loop（跑 TestClient 触发的 app）——即 **跨线程的双 loop**。

### pytest-asyncio 的角色

`pytest-asyncio` 为 `async def test_...` 创建/管理 event loop（本项目 `asyncio_mode = auto`）。  
**仅把测试改成 `async def` 不能解决 TestClient 问题**：`TestClient.post()` 仍是同步 API，app 仍在 Portal 的 loop 里跑，与 pytest loop 分离。

### httpx.AsyncClient 的差异

```python
@pytest.mark.asyncio
async def test_register(client):
    response = await client.post("/auth/register", json={...})
```

`await client.post(...)` 在 **pytest-asyncio 的同一 loop** 里直接 `await` ASGI app，**不经过 Portal 换线程**，与 `get_db()` / 全局 `_engine` 的 loop 一致。

## 全局 `_engine` 为何触发冲突

`app/infra/database.py` 使用进程级单例：

```python
_engine: AsyncEngine | None = None

def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url)
    return _engine
```

要点：

1. **`create_async_engine()` 是同步工厂**，创建时不绑定 loop。
2. **第一次在该 loop 上 `await` 连接池/连接**（如 `await session.execute(...)`）时，asyncmy 的 Future/socket 绑定到 **当前 running loop**。
3. 之后 **任何其他 loop** 复用同一 `_engine` 做 async I/O → `attached to a different loop`。

### 典型失败时间线（修复前）

```text
1. test_get_db_select_one（Loop A = pytest-asyncio）
   async for session in get_db():
       await session.execute(...)    ← 全局 _engine 首次绑定 Loop A ✓

2. test_register_duplicate（Loop B = TestClient Portal）
   client.post("/auth/register")
     → Loop B: await get_db() → 复用 _engine
     → await session.execute(...)  ← 💥 Loop B 使用 Loop A 的 Future
```

### 执行顺序敏感

| 测试 | 是否调用全局 get_db | 结果 |
|------|---------------------|------|
| 密码长度 422 | 否（Pydantic 拦截） | 过 |
| health / JWT 单元 | 否 | 过 |
| readiness | 否（service 内独立 engine） | 过 |
| register / login / me | 是 | 挂（若 _engine 已在另一 loop 初始化） |

故同一套代码 **按 pytest 收集顺序不同，通过/失败可能变化**——`test_get_db_select_one` 是常见「污染源」。

### 上下文管理器为何仍出现连接泄漏告警

`get_db()` 的 `try/finally: await session.close()` 与 `with TestClient(app)` 只能保证 **正常路径** 有序退出。跨 loop 异常时：

1. `session.execute` 先抛 `RuntimeError`；
2. `finally` 里 `close()` 在错误 loop/损坏连接上再次失败；
3. Portal loop 关闭，全局 `_engine` 仍持有旧 loop 上的连接 → SAWarning / `Event loop is closed`。

根因仍是 loop 混用，而非「忘记写 with」。

## 为何生产环境无此问题

Uvicorn 单 worker 内 **一个 event loop** 处理所有请求；全局 `_engine` 连接池与请求在同一 loop，设计成立。

问题仅出现在 **测试人为引入第二个 loop**（TestClient Portal）时。

## 为何不全面保留 TestClient

| TestClient 仍有市场的原因 | 本项目选择 AsyncClient 的原因 |
|---------------------------|-------------------------------|
| 同步测试写法简单（`def test` + 无 await） | 项目已是 async FastAPI + async SQLAlchemy |
| 文档/历史示例多 | 需与 `get_db()` 同 loop，避免隐性双 loop |
| 不碰 async 单例时往往够用 | 统一 fixture，降低误用 TestClient 测 DB 端点的风险 |

health/readiness 虽可不碰 DB，为 **一致性** 亦改为 `AsyncClient`。

## 本项目测试约定（实施后）

```python
# tests/conftest.py
@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
```

- 所有 HTTP integration 测试：`@pytest.mark.asyncio` + `await client.get/post(...)`。
- integration 测试 autouse：`reset_engine()` 前后清理全局连接池。
- 纯单元测试（如 `tests/infra/test_auth.py`）：不启 client，直接测函数。

## 参考

- [FastAPI — Testing async code](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Starlette — TestClient](https://www.starlette.io/testclient/)（同步 façade，内部 AnyIO Portal）
- [AnyIO — Calling async code from threads](https://anyio.readthedocs.io/en/stable/threads.html)
- 本项目：`app/infra/database.py`（`reset_engine`）、`tests/conftest.py`
- 相关 ADR：`docs/decision/测试与数据库策略.md`、`docs/decision/单例与线程锁在FastAPI中的适用场景.md`（Engine 单例在生产合理，测试需 loop 隔离）
