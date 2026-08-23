## Context

MySQL/Redis 由 **一个** process-compose 监督；`devbox services up <单名>` 在监督器已存在时不能追加。PostgreSQL 因 `PGHOST=127.0.0.1` 与插件 `postgres -k "$PGHOST"` 冲突，改走 `pg_ctl` + `postgres-data/`。数据目录三处、`db:*` 名不副实、`task ci` 三 deps 并行抢锁。本切片只动本地 devbox 运维与文档；CI 仍用 service container。无跨域 service、无新表。

## Goals / Non-Goals

**Goals:**

- 三库同一个监督器；`PGHOST` 为 socket 目录，TCP 仍 `127.0.0.1:5433`。
- 数据根 `db-data/`；Task 总闸/分库；竞态纪律写进 ADR-002。
- readiness 测例去掉组合爆炸，单点 503 + 一条真连 200。

**Non-Goals:**

- 改 CI workflow、业务 API、AOF、media 目录、旧数据迁移。

## Decisions

### 1. 冷启动一次点齐三名

**选择**：共享函数「确保监督器」：未运行则 `devbox services up mysql redis postgresql -b`；已运行则忽略 `already running`。然后 `start <自己>` + 既有 ping / 建库。`db:up` 只调一次 `up` 三名，再对三库做 ping+建库（或依次调三个 `*:up`，但 **禁止并行三个 `up`**）。

**理由**：process-compose 单例；官方 `start` 用来启用已注册的 Disabled 进程。

**替代**：并行 Task deps 各 `up` 一个 → 正是现状竞态。裸 `up -b` → 会带上插件 `postgresql` 的错误 env，且可能拉起 `mysql_logs`。

### 2. `PGHOST` 目录 vs 应用 TCP

**选择**：

```text
PGDATA=./db-data/postgres/data
PGHOST=./db-data/postgres/run    # 仅 -k socket
PGPORT=5433
AI_DATABASE_URL=...@127.0.0.1:5433/...
```

`pg:up`：无 `PG_VERSION` 则 `initdb`；`start postgresql`；`pg_isready -h 127.0.0.1 -p 5433`；建角色/双库/`vector`。不再 `pg_ctl start`。

**理由**：迁就插件，不改应用连接串。

**替代**：继续 `pg_ctl` → 监督器仍裂。`PGHOST=127.0.0.1` → `-k` 非法。

### 3. `db-data/` 与 Task 语义

```text
db-data/
  mysql/
  redis/
  postgres/data
  postgres/run
```

| Task | 行为 |
|------|------|
| `db:up` / `down` / `reset` | 三库；reset = down + `rm -rf db-data/` + up |
| `mysql\|redis\|pg`:`up\|down\|reset` | 只动对应子目录；down = `services stop <名>` |

`ci` / `dev` / `test:reports` → 只 `deps: db:up`（**dev 将顺带起 PG**，readiness 不再 503）。`migrate` → `mysql:up`；`migrate:ai` → `pg:up`。

**替代**：`db:up` 仍只表示 MySQL → 名实继续错。

### 4. 竞态写进 ADR-002，不新开 ADR

**选择**：在 ADR-002 增补一节（决策 10）：单例、`up` vs `start`、总闸一次三名、分库 down 禁止无名字 `stop`；并改 §1/§6/§7/§9 的路径与 Task 表。日期旁注本 change。

**理由**：这是「本地提供形式」的修正，不是新原则。

### 5. readiness 只留单点 + 一条 200

**删除测例**：`200_when_mysql_ok`、`200_when_mysql_and_redis_both_ok`、`200_when_all_three_ok`、`503_when_both_unavailable`、`503_when_all_three_unavailable`。

**保留**：各单点 503、content-type、checks 含 postgresql、PG 真探测正反、`200_with_all_real_deps`。

**理由**：AND 聚合由三条单点证明；组合不增加信息。

### 6. 脚本契约测（红门禁）

新增 `tests/ops/test_devbox_compose_contract.py`（读文件、无 I/O）：`devbox.json` 的 `PGHOST` 不是 IP；路径含 `db-data`。实现前红、实现后绿。不为 Taskfile 写 integration。

## Risks / Trade-offs

- [旧 `postgres-data` 仍在跑] → apply 前 `pg:down`；文档写删旧目录。
- [插件 `-k` 与 5433 仍连错] → `pg_isready` 必须带 `-h 127.0.0.1 -p 5433`。
- [`task dev` 变重] → 可接受；要轻量用 `mysql:up` + `redis:up`。
- [分库 down 误用 `services stop`] → 脚本与 ADR 写死带名。

## Migration Plan

1. 红：收 readiness + 契约测失败。
2. env / conf / 脚本 / Taskfile。
3. ADR-002 + README / rules。
4. 绿契约测 + readiness；`task db:up` 手验；`task ci`。
5. 回滚：恢复旧脚本与三目录名（不推荐）。

## Open Questions

无。数据丢弃、总闸语义、竞态进 ADR-002、readiness 收口已在 explore 拍板。
