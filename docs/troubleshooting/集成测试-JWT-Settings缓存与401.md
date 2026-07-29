# 集成测试 JWT / Settings 缓存与 401

## 场景

FastAPI integration 测试使用 **httpx AsyncClient** 走真实 auth 流程（register → 拿 token → 带 Bearer 调 `/shops`、`/products` 等）。  
项目里 `get_settings()` 是 **`@lru_cache` 单例**；`.env` 中为 **dev** JWT 密钥，`tests/conftest.py` 为 integration **强制覆盖 test 密钥**。

典型触发：

- 全量 `task test` / `task ci`（65+ 项），catalog 用例如 `test_get_public_products_returns_only_published_active`
- 测试 refactor 后使用 `ShopOwnerContext` / `RegisterResult`，断言仅 `status_code == 201` 而未检查 `headers`
- `tests/infra/test_auth.py` 的 autouse 仅 `get_settings.cache_clear()`，与 conftest integration autouse 规则不一致

## 问题

### 主错误

```text
assert 401 == 201
```

常见于：

- `assert shop_owner.status_code == 201`（开店 `POST /shops` 未认证）
- `_create_product` 内 `assert response.status_code == 201`（`POST /products` 未认证）
- `_create_category_for_product` 内 `assert result.status_code == 201`（admin `POST /categories` 未认证）

HTTP 401 在业务里表示 **「未认证」**，不一定是 JWT 密钥问题（见下文「其他 401 成因」）。

### 表现

| 运行方式 | 常见结果 |
|----------|----------|
| 单文件 / 单用例 | 通过 |
| 全量 pytest | 偶发或稳定失败（视 conftest 版本与环境） |
| 重构中间态（helper 未 `_ensure`） | 更容易失败 |

**不是 pytest fixture 依赖乱序**：单个测试内 autouse → client → fixture → 测试体的顺序是确定的。

## 根因

### 1. 两套 JWT 密钥（最易误解的一点）

| 来源 | 环境变量 | 典型用途 |
|------|----------|----------|
| `.env` | `dev-only-change-me-use-at-least-32-chars!!` | 本地 dev |
| `tests/conftest.py` | `test-secret-key-at-least-32-bytes!!` | integration 测试 |

「`.env` 里的 JWT 一直没改」≠「测试运行时用的 secret 始终相同」。  
integration 测试依赖 conftest **覆盖** `os.environ["JWT_SECRET_KEY"]`。

### 2. `cache_clear()` 本身不会搞坏 JWT

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`get_settings.cache_clear()` 之后，下次 `get_settings()` **会** new 一个 `Settings()`——这是预期行为。

验签失败的条件是：

```text
签发 token 时 get_settings().jwt_secret_key == A
cache_clear() 后重新 get_settings().jwt_secret_key == B
A ≠ B  →  旧 token 验签 401
```

若每次 `_configure_integration_test_env()` 都把 `JWT_SECRET_KEY` 设回 **test secret**，则 A、B 应相同，**清缓存不会单独导致 401**。

### 3. 跨测试 / 跨 autouse 规则（全量跑时）

`tests/conftest.py` 的 integration autouse **仅**对带 `@pytest.mark.integration` 的用例在开头调用 `_ensure_integration_auth_env()`：

```python
if request.node.get_closest_marker("integration") is None:
    yield
    return
_ensure_integration_auth_env()
```

`tests/infra/test_auth.py` 等 **无** integration marker 的模块不会走上述逻辑；若其 autouse 只做 `cache_clear()` 而不恢复 test env，与 integration 测试交替执行时，理论上存在 **重新加载 Settings 时读到 dev secret** 的风险（取决于 `os.environ` 是否仍被 conftest 覆盖）。

### 4. autouse 只包「测试边界」，不包 helper 内每一步

`_reset_global_database_engine` 在 integration 测试 **开头/结尾** 运行，**不会**插在 `register_and_open_shop()` 内部的 `register_user()` 与 `create_shop()` 之间。

通常无妨：helper 执行期间若无人 `cache_clear()`，同一 `Settings` 缓存贯穿 register → 开店。

重构后在 conftest helper 内增加 `_ensure_integration_auth_env()` 属于 **加固**（register 与开店之间再对齐 env），不是 fixture 顺序写错。

### 5. 与异步的关系

- `get_settings()` 是 **同步** `@lru_cache`，与 `@pytest.mark.asyncio` 无直接因果
- autouse 里的 `reset_engine()` 解决的是 **DB 连接池 / event loop**，不是 JWT
- 除非 pytest-xdist 多进程或并发修改 `os.environ`，不宜把 401 主要归因于「异步测试」

### 6. 重构后更易误判为 JWT 问题

Typed `ShopOwnerContext` 若注册「半成功」（`status_code == 201` 但 `body is None` → `headers == {}`），测试只断言 `status_code` 会通过，后续 `POST /products` 才 401——**与密钥无关，是没带 token**。

## 其他 401 成因（非 JWT 缓存）

| 成因 | 说明 |
|------|------|
| 空 `headers` | Context 半成功，`shop_owner.headers` 为空 |
| `require_admin` 查无用户 | DB 未 migrate / seed admin 缺失，返回 401（非 decode 失败） |
| 未带 Bearer | 迁移测试直连 `client.post` 时漏传 `headers` |

排查时看失败栈是在 **fixture 开店** 还是 **测试体 create_product**。

## 解决

### 1. import app 前注入 test env（已有）

```python
_configure_integration_test_env()
_reset_settings_cache()
from app.main import app
```

### 2. integration 测试 autouse 开头 `_ensure`（已有）

每个 `@pytest.mark.integration` 测试开始前：

```python
def _ensure_integration_auth_env() -> None:
    _configure_integration_test_env()
    _reset_settings_cache()
```

### 3. auth 相关 helper / fixture 内 `_ensure`（test-schema-typing 已加）

`register_user`、`login_user`、`create_shop`、`create_category`、`register_and_open_shop`、`admin_auth_headers` 等在 HTTP 前调用 `_ensure_integration_auth_env()`。

### 4. 非 integration 单测（如 `test_auth.py`）autouse 与 conftest 对齐

```python
from tests.conftest import _ensure_integration_auth_env

@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    _ensure_integration_auth_env()
    yield
    _ensure_integration_auth_env()
```

避免「只 `cache_clear`、不恢复 test JWT env」。

### 5. Context 断言收紧

除 `status_code` 外，成功路径应检查：

```python
assert shop_owner.status_code == 201
assert shop_owner.shop is not None
assert shop_owner.headers
assert admin_auth_headers.status_code == 200
```

避免半成功拖到后续步骤才报 401。

### 6. `register_and_open_shop` 失败路径

注册未完整成功（`body is None`）时，**不得**将 `ShopOwnerContext.status_code` 设为 201 且 `headers` 为空；应使 `status_code` 反映失败，便于断言在 fixture 阶段暴露。

## 验证

```bash
devbox run -- task db:up
devbox run -- task migrate
devbox run -- task ci
```

重点用例：

- `tests/catalog/test_public_products.py::test_get_public_products_returns_only_published_active`
- `tests/infra/test_auth.py`（与 integration 全量交替跑）
- `tests/user/test_register.py`、`test_login.py`、`test_me.py`

全量应 65 passed（数量随项目增长可能变化）。

## 关键概念

- **`get_settings()`**：进程级 `@lru_cache`；`cache_clear()` 只丢缓存，不保证下次加载的 secret 与签发时相同
- **test vs dev JWT**：integration 必须覆盖 `.env` dev 密钥
- **token 字符串**：fixture 里签发的 Bearer；每个测试 function-scope fixture 应重新签发，不跨用例复用
- **401**：未认证；可能是 JWT 密钥不一致、空 headers、或 admin 用户不存在
- **autouse 边界**：保证测试开头 env 一致；helper 内多步 HTTP 若中间有 `cache_clear`，须配合 `_configure_integration_test_env()`

## 关联文件

- `tests/conftest.py` — `_configure_integration_test_env`、`_ensure_integration_auth_env`、integration autouse
- `tests/infra/test_auth.py` — JWT 单元测试 autouse（应对齐 `_ensure`）
- `app/infra/config.py` — `get_settings()` 单例
- `app/infra/auth.py` — `create_access_token` / `decode_access_token`
- `.env` — dev `JWT_SECRET_KEY`（勿与 test secret 混淆）
- `openspec/changes/test-schema-typing/` — Context/Result 重构与 DoD

## 重构教训（test-schema-typing）

工程化（`builders` / `Context` / `Result`）**不替代** env 与 Settings 纪律：

1. 类型化后断言要从 `result["json"]` 改为属性，并 **增加** `headers` / `shop` 等非 None 检查
2. 迁移后测试里直连 `client.post` 的路径不经过 conftest helper，仍依赖 fixture 签发的 token 与 test env 一致
3. 老 JWT 防护（import 前 env、integration autouse）**未被删除**；重构暴露的是 **断言变少 + 多步 HTTP + 跨模块 autouse 规则差异**，而非 fixture 依赖乱序

## 参考

- [docs/troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md](./集成测试-AsyncClient与EventLoop线程冲突.md) — engine / loop 隔离（互补，非 JWT）
- [docs/decision/测试与数据库策略.md](../decision/测试与数据库策略.md)
- `.cursor/rules/async-integration-testing.mdc`
