# 单例与线程锁在 FastAPI 中的适用场景

> **性质**：个人学习笔记（不进 OpenSpec spec）；与 `user-auth` change 相关，解释 JWT 鉴权为何不用 Singleton `AuthHandler`。

- **状态**：已采纳（本项目实践）
- **日期**：2026-07-13
- **背景**：实现 `app/infra/auth.py` 时，常见教程会封装 `AuthHandler` / `JWTManager` 单例类，集中持有 secret、algorithm 并提供 `create_token` / `decode_token`。需明确：在 FastAPI + asyncio 下，哪些资源值得单例化，哪些逻辑应保持无状态纯函数。

## 决策

### 1. JWT 编解码：不用 Singleton，使用无状态纯函数

`app/infra/auth.py` **不** 引入 `AuthHandler` 单例类；token 签发与校验实现为模块级函数，每次调用从 `get_settings()` 读取配置：

```python
# 示意 — 实际见 app/infra/auth.py
def create_access_token(user_id: uuid.UUID) -> str: ...
def decode_access_token(token: str) -> uuid.UUID: ...
```

**理由**：

1. **JWT 本身无状态**：secret、issuer、algorithm 来自 Settings，不需要在对象实例上缓存可变业务状态；PyJWT 的 `encode` / `decode` 已是纯函数式 API。
2. **配置已有单例入口**：`get_settings()` 经 `@lru_cache` 缓存，重复读取成本低，无需再包一层 AuthHandler 单例。
3. **测试更简单**：直接测函数 + mock `get_settings`，不必 reset 单例或处理测试间污染。
4. **避免伪「面向对象」**：把两个函数硬塞进类，只会增加 indirection，不带来生命周期收益。

### 2. 何时适合单例（或「进程内唯一实例」）

| 场景 | 本项目做法 | 为何需要唯一实例 |
|------|-----------|-----------------|
| **Settings** | `get_settings()` + `@lru_cache` | 解析 `.env` 有 I/O；配置在进程内不变，缓存即可 |
| **AsyncEngine / Session 工厂** | `get_engine()` / `get_session_factory()` 懒加载全局变量 | 连接池昂贵，应全进程共享；SQLAlchemy 文档推荐 engine 复用 |
| **OAuth2PasswordBearer 实例** | 模块级 `oauth2_scheme = OAuth2PasswordBearer(...)` | FastAPI 依赖注入需要同一 scheme 对象注册 OpenAPI |

共同点：**持有昂贵或应全局一致的资源**，且**无 per-request 可变状态**。

### 3. 线程锁：asyncio 下通常不需要为 JWT 加锁

FastAPI 默认在 **asyncio 事件循环** 中处理请求（Uvicorn worker）。JWT 编解码是 CPU 级短计算，不共享可变内存，**无竞态**，不需要 `threading.Lock`。

| 情况 | 是否需要锁 |
|------|-----------|
| 纯函数 JWT encode/decode | 否 |
| 只读 Settings（lru_cache 后不变） | 否 |
| 懒初始化 `_engine`（多协程并发首次调用） | 理论上可能 double-init；CPython GIL + SQLAlchemy 内部处理使实践中可接受；若严格可 `asyncio.Lock` 或模块 import 时初始化 |
| 多 **进程** worker（Uvicorn `--workers 4`） | 每进程独立内存，单例不跨进程共享；连接池每进程一份，属预期行为 |

**注意**：若在同步路由中阻塞或使用 `run_in_executor` 操作**可变共享缓存**，才考虑 `threading.Lock`；本 MVP 无此场景。

### 4. 与「单例反模式」的边界

以下做法在本项目中**不采用**：

- `class AuthHandler(metaclass=Singleton)` 仅为了「看起来专业」
- 在 Singleton 内缓存「当前用户」——用户状态属于请求 scope，应走 FastAPI `Depends`，不能进进程单例
- 用线程锁保护 JWT 函数——无共享写状态，锁只会拖慢吞吐

## 本项目对照

```text
app/infra/config.py     get_settings()          ← @lru_cache 单例（适合）
app/infra/database.py   get_engine()            ← 懒加载单例（适合）
app/infra/auth.py       create_access_token()   ← 无状态函数（适合）
                        decode_access_token()
                        get_current_user_id()   ← 请求级 Depends，非单例
```

## 后果

- 新增 token 类型（如 refresh token）时，优先增加函数或独立模块，而非膨胀 AuthHandler 类
- 若未来引入 token 黑名单（Redis），**黑名单客户端**可单例化，**校验逻辑**仍保持函数 + 注入客户端
- 多 worker 部署时，每个 worker 独立 Settings/engine；JWT 校验不依赖内存共享，水平扩展友好

## 相关文档

- [user-auth design §3 JWT](../../openspec/changes/user-auth/design.md)（不用 Singleton AuthHandler）
- [app/infra/config.py](../../app/infra/config.py)（`get_settings` 单例）
- [app/infra/database.py](../../app/infra/database.py)（engine 懒加载单例）
