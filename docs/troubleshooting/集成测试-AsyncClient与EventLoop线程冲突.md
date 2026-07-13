# 集成测试 AsyncClient 与 Event Loop 线程冲突

## 场景

FastAPI + **async SQLAlchemy**（全局 `get_engine()` 单例）+ pytest integration 测试。HTTP 测试若使用 Starlette **`TestClient`**（同步 `client.post()`），且与 `@pytest.mark.asyncio` 或 `get_db()` 混跑。

典型触发：`tests/user/` 注册/登录/me 等需 **`Depends(get_db)`** 的用例；`test_get_db_select_one` 若在 TestClient 测试之前运行，易成为「污染源」。

## 问题

### 主错误

```text
RuntimeError: Task ... got Future <Future pending> attached to a different loop
```

### 连锁报错

```text
readexactly() called while another coroutine is already waiting for incoming data
SAWarning: garbage collector is trying to clean up non-checked-in connection
RuntimeError: Event loop is closed
```

### 表现

| 测试类型 | 是否调用全局 `get_db` | 常见结果 |
|----------|----------------------|----------|
| 密码长度 422 等纯校验 | 否 | 通过 |
| JWT 单元 / health | 否 | 通过 |
| readiness（独立 engine） | 否 | 通过 |
| register / login / me | 是 | **失败** |

**执行顺序敏感**：同一套代码按 pytest 收集顺序不同，通过/失败可能变化。

## 根因

1. **`TestClient` 使用 AnyIO BlockingPortal**：同步测试线程无 loop；app 在 **Portal 后台线程的另一 event loop** 里 `await`。
2. **全局 `_engine` 连接池绑定首次使用的 loop**：`create_async_engine()` 是同步工厂；**第一次**在该 loop 上 `await session.execute(...)` 时，asyncmy Future/socket 绑定当前 running loop。
3. **跨 loop 复用同一 `_engine`**：Loop B 上的 TestClient 请求复用 Loop A 上初始化的连接池 → `attached to a different loop`。
4. **上下文管理器无法兜底**：跨 loop 异常后 `session.close()` 再次失败，连接未归还 pool，触发 SAWarning / `Event loop is closed`。

```text
Loop A（pytest-asyncio）     test_get_db_select_one → get_db() → _engine 首次绑定
Loop B（TestClient Portal）  client.post → get_db() → 复用 _engine → 💥
```

**注意**：仅把测试改成 `async def` **不能**解决——`TestClient.post()` 仍是同步 API，app 仍在 Portal loop 里跑。

生产环境 Uvicorn 单 worker 单 loop，无此问题。

## 解决

### 1. HTTP 集成测试改用 httpx AsyncClient

与 `pytest-asyncio` **共用同一 event loop**，不经过 BlockingPortal：

```python
@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

@pytest.mark.integration
@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    response = await client.post("/auth/register", json={...})
    assert response.status_code == 201
```

### 2. integration 测试前后重置全局 engine

`app/infra/database.py` 提供 `reset_engine()`；`tests/conftest.py` autouse fixture 在 `@pytest.mark.integration` 测试前后调用，避免连接池跨 loop 残留。

### 3. 不污染全局单例的 DB 测试用独立 engine

`test_get_db_select_one` 使用本地 `create_async_engine()`，不调用全局 `get_db()` 初始化 `_engine`（readiness service 同理）。

### 4. 禁止用 TestClient 测 I/O 密集型路径

见 `.cursor/rules/async-integration-testing.mdc`：async 代码须 async 测试；BlockingPortal 只适合纯计算、无全局 async 单例的场景。

## 验证

修复后全量 pytest 应通过（本项目 24 项），且不再出现 `StarletteDeprecationWarning`（TestClient 导入 httpx 弃用警告）：

```bash
task db:up
# DATABASE_URL 指向 ecommerce_test，JWT_SECRET_KEY 已设置
task ci
```

失败用例应全部变为通过，尤其：

- `tests/user/test_register.py`
- `tests/user/test_login.py`
- `tests/user/test_me.py`

## 关键概念

- **TestClient**：ASGI 直调、不启 HTTP 服务器；内部 Portal 在**另一线程/loop** 跑 async app。
- **BlockingPortal**：sync 测试线程 ↔ async app 的桥梁；引入双 loop。
- **pytest-asyncio**：为 `async def test` 管理 loop（本项目 `asyncio_mode = auto`）。
- **AsyncClient + ASGITransport**：在同一 loop 内 `await` app，与 `get_db()` 一致。
- **全局 AsyncEngine**：进程单例合理（生产）；测试须 loop 隔离或 `reset_engine()`。

## 关联文件

- `tests/conftest.py` — async `client` fixture、`reset_engine` autouse
- `app/infra/database.py` — `get_engine()`、`reset_engine()`
- `tests/infra/test_database.py` — 独立 engine，不污染全局单例
- `.cursor/rules/async-integration-testing.mdc` — 测试纪律
- `docs/decision/测试与数据库策略.md` — 双库与 integration 惯例
- `docs/decision/单例与线程锁在FastAPI中的适用场景.md` — Engine 单例在生产中的合理性

## 参考

- [FastAPI — Testing async code](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Starlette — TestClient](https://www.starlette.io/testclient/)
- [AnyIO — Calling async code from threads](https://anyio.readthedocs.io/en/stable/threads.html)
