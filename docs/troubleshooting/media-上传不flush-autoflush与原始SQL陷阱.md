# media 上传不 flush：autoflush 覆盖边界与生产持久化缺口

## 场景

media-storage 交付后，media-attach 阶段新增引用/元数据测试，用**原始 SQL** 模拟业务 attach：

- `tests/media/test_delete_referenced.py`：`text("UPDATE users SET avatar_media_id=...")` 模拟 avatar 引用
- `tests/media/test_get_media_metadata.py`：`text("UPDATE media_assets SET visibility='public'")` 模拟 `mark_public`

典型触发：

- `@pytest.mark.integration` media 用例上传后立即用 `db_session.execute(text(...))` 改库
- 全量 media 套件（`tests/media/` + `tests/unit/media/`）

## 问题

| 现象 | 表现 |
|------|------|
| avatar 引用 → DELETE 409 | setup 抛 `IntegrityError (1452) Cannot add or update a child row ... FOREIGN KEY (avatar_media_id) REFERENCES media_assets(id)` |
| public media 匿名 GET → 200 | 返回 **403** 而非 200（`UPDATE` 命中 0 行，media 仍 owner_only） |
| 深层隐患 | **生产 `POST /media` 数据直接丢失**（见「根因 3」） |

**不要只当作测试失败**——它是 media-storage 遗留的真实持久化 bug 在测试里的显影。

## 根因

### 1. upload 只 `add` 不 flush/commit（真 bug）

```python
# 修复前 MediaRepository.insert
async def insert(self, asset: MediaAsset) -> None:
    self._session.add(asset)          # 只进待办清单，INSERT 不执行
```

SQLAlchemy 里 `session.add(obj)` **不执行 SQL**。INSERT 真正落库靠两种机制之一：
1. **autoflush**：后续 **ORM 查询**前自动同步待办；
2. 显式 `flush()` / `commit()`。

### 2. autoflush 只对 ORM 查询触发，原始 SQL 不触发

实测（会话配置同 conftest：`AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)`）：

| 语句 | 触发 autoflush？ |
|------|-----------------|
| `execute(select(MediaAsset))` — ORM 查询 | ✅ |
| `execute(text("SELECT ..."))` — 原始 SQL | ❌ |
| `execute(text("UPDATE ..."))` — 原始 SQL | ❌ |

设计语义：autoflush 保证 **ORM 对象图一致性**——"你要 ORM 查，我保证 pending 先落库"。原始 SQL 是"绕过 ORM 直接对 DB 说话"，SQLAlchemy 不替你擅自 flush。

因此模拟 attach 的 `text("UPDATE users SET avatar_media_id=...")` 执行时，pending 的 media_assets 行**还没落库** → 外键找不到父行 → 1452。

### 3. 测试共享会话掩盖了「没 commit」的事实（生产 vs 测试）

| | 生产 | 测试 |
|---|---|---|
| `get_db` | 每请求**新建** session | conftest **override** 返回**同一个** session |
| 请求结束 | `session.close()` → 未 commit 就**回滚** | 不 close，继续共享 |
| 上传不 commit | **数据丢失** | pending 留在共享 session |
| 后续 HTTP 读 | 新 session 只读已提交数据 | 同一 session → ORM 查询 → **autoflush** 落库 → 可见 |

「上传再 HTTP 读能读到」**只在测试里成立**。生产里 `POST /media` 结束即回滚，数据蒸发——CI 没抓到是因为集成测试共享外层事务 + 结束 `rollback()`，从不验证「其它连接能否看到」。

### 4. savepoint 是「回滚边界」，不是「可见性」

```python
trans = await conn.begin()   # 外层事务
session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
```

`join_transaction_mode="create_savepoint"`：service 调 `session.commit()` 时**不提交外层事务**，而是开一个 SAVEPOINT 再释放。测试结束 `trans.rollback()` 整体撤销 → 零残留。**它跟数据可不可见无关**——可见性来自「同一会话 + autoflush」。

### 5. expire_on_commit=False → identity map 旧值

即使修了 flush，`get_detail` 仍可能读到旧值：原始 SQL 改了 visibility，但共享 session 的 **identity map** 缓存着旧对象（`expire_on_commit=False` 不自动过期），ORM 查询命中缓存返回旧值 → 403。

## 解决

### 1. `MediaRepository.insert()` 补 flush

```python
async def insert(self, asset: MediaAsset) -> None:
    self._session.add(asset)
    await self._session.flush()   # ← 新增：行在本事务内物理可见
```

用 `flush()` 而非 `commit()` 是刻意的：commit 会打破业务层原子性（attach 流程 `assert → 写 FK → mark_public` 应由业务层统一提交），flush 只让行在**当前事务内**可见。

### 2. `get_detail` 读最新持久化状态

`get_by_id(..., fresh=True)` 用 `populate_existing=True` 强制从 DB 刷新，忽略 identity map 缓存（生产每请求新 session，无损；只影响共享 session 的测试场景）。

### 3. 附：直接运行 pytest 的环境陷阱（本轮同遇）

直接 `uv run pytest`（不经 `task test`）且不带 `APP_ENV_FILE=.env.test` 时，`app/infra/config.py` 的 `_ENV_FILE` 在**模块 import 时**冻结为 `.env`（dev）——conftest 的 `bootstrap_test_env()` 用 `setdefault` 设 env 太晚。于是 Settings 读到 dev 配置：无 `SMS_OTP_FIXED_CODE` → mock 发随机 OTP ≠ helper 固定 `"123456"` → 注册 422。**应带 `APP_ENV_FILE=.env.test` 运行**（等价 `task test`）。

## 验证

```bash
APP_ENV_FILE=.env.test devbox run -- uv run pytest tests/media/ tests/unit/media/ -q --tb=no -rN 2>/dev/null
```

预期：`53 passed, 2 errors`（2 error = logo/product 引用 409，阻塞于 §5.1 catalog wire：`POST /shops` 仍访问已删除的 `logo_url`，非 media 域缺陷）。

关键用例：

- `tests/media/test_delete_referenced.py::test_delete_media_referenced_by_avatar_returns_409`（flush 修复）
- `tests/media/test_get_media_metadata.py::test_public_media_metadata_anonymous`（populate_existing 修复）
- `tests/unit/media/test_visibility.py`（upload 签名迁移后仍绿）

## 关键概念

- **Session 状态机**：`add()` 进待办（pending）→ `flush()` 执行 SQL 变 persistent → `commit()` 固化（对其它连接可见）。
- **autoflush 触发规则**：ORM 查询前触发；原始 text SQL 不触发（实测）。
- **flush vs commit**：flush 不提交事务、当前事务内可见、可回滚；commit 提交事务、数据固化、不可回滚。
- **savepoint**：测试的回滚边界机制，不是可见性机制。
- **identity map**：session 内按主键缓存对象；`expire_on_commit=False` 下 commit 后不自动过期，原始 SQL 改动需 `populate_existing` 才可见。
- **测试通过 ≠ 生产正确**：共享会话 + autoflush 会掩盖「从不 commit」的持久化缺口。

## 关联文件

- `app/media/repository.py` — `insert()` flush、`get_by_id(fresh=)`、`count_references()`（text SQL 查三表，不跨域 import ORM）
- `app/media/service.py` — `get_detail()`（fresh 读）、`_load(fresh=)`
- `tests/conftest.py` — `db_session` / `integration_client`：共享会话 + SAVEPOINT + override
- `app/infra/config.py` — `_ENV_FILE` 模块 import 时冻结
- `app/infra/database.py` — `get_db` 生产每请求新建 session

## 参考

- [docs/troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md](./集成测试-AsyncClient与EventLoop线程冲突.md) — 共享会话 / engine 隔离的互补踩坑
- [docs/decision/ADR-002-测试与数据库策略.md](../decision/ADR-002-测试与数据库策略.md)
- [docs/decision/ADR-003-测试架构-四层分层与数据流约束.md](../decision/ADR-003-测试架构-四层分层与数据流约束.md)
