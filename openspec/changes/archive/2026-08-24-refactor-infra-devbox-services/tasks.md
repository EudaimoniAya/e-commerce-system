## 1. TDD — 失败测试（红）

> 只写测、不写实现。§1 完成前不得开始 §2–§4。

- [x] 1.1 收口 `tests/ops/test_readiness.py`：删除 `200_when_mysql_ok`、`200_when_mysql_and_redis_both_ok`、`200_when_all_three_ok`、`503_when_both_unavailable`、`503_when_all_three_unavailable`。保留各单点 503、content-type、checks 含 postgresql、`is_postgresql_ready` 正反、`200_with_all_real_deps`。**不改** readiness 实现
- [x] 1.2 新增 `tests/ops/test_devbox_compose_contract.py`（只读文件、无进程 I/O）：`devbox.json` 的 `PGHOST` 不是 IP；`devbox.json` 与 MySQL/Redis 本地配置路径含 `db-data`。**不编写** env / 脚本 / Taskfile
- [x] 1.3 `uv run pytest tests/ops/test_devbox_compose_contract.py -q` 确认失败（红）

## 2. 配置、脚本与 Taskfile（绿）

- [x] 2.1 改 `devbox.json`：`PGDATA=./db-data/postgres/data`、`PGHOST=./db-data/postgres/run`（目录，非 IP）、`PGPORT=5433`；MySQL/Redis 数据路径指向 `db-data/`
- [x] 2.2 改 `devbox.d` 下 MySQL/Redis 本地 conf，数据目录落到 `db-data/mysql/`、`db-data/redis/`
- [x] 2.3 抽出共享「确保监督器」：未运行则一次 `devbox services up mysql redis postgresql -b`，已运行则忽略 already-running；分库 `*:up` 随后 `start <自己>` + 既有 ping/建库。`pg:up`：无 `PG_VERSION` 则 `initdb`；`pg_isready -h 127.0.0.1 -p 5433`；不再 `pg_ctl start`。分库 `*:down` 必须 `services stop <名>`
- [x] 2.4 `Taskfile.yml`：`db:up|down|reset` 改为三库总闸（reset = down + `rm -rf db-data/` + up）；补齐 `mysql|redis|pg` 的 `up|down|reset`。`ci` / `dev` / `test:reports` / `ai:reindex-*` 只 deps **`db:up`**（禁止并行多个 `*:up`）。`migrate` deps **`mysql:up`**；`migrate:ai` 仍 `pg:up`
- [x] 2.5 `.gitignore` 增加 `db-data/`；保留旧 `mysql-data/`、`postgres-data/` 忽略以防残留
- [x] 2.6 跑绿 §1.2；保留的 readiness 测例仍绿
- [x] 2.7 脚本归拢：`devbox_*.sh` 迁入 `scripts/devbox/` 并去 `devbox_` 前缀（`services.sh`、`db_{up,down,reset}.sh`、`{mysql,redis,pg}_{up,down,reset}.sh`）；同步 Taskfile 与 README / architecture / ADR-002 / troubleshooting / `.cursor` 的路径引用；ADR-006 的 `scripts/devbox_*` glob 改 `scripts/devbox/**`

## 3. ADR-002 与文档

- [x] 3.1 **增补** `docs/decision/ADR-002-测试与数据库策略.md` **决策 10**（不新开 ADR）：process-compose 单例、`up` vs `start`、总闸一次点齐三名、禁止并行各 `up` 一个服务、分库 down 禁止无名字 `stop`；旁注本 change。同步改 §1/§6/§7/§9 的路径与 Task 表（`db:*` = 三库，`db-data/`）
- [x] 3.2 更新 README、`docs/architecture.md`、`.cursor/rules`（含 `devbox-run-for-db-ops.mdc`）、`CLAUDE.md`、`openspec/config.yaml`：凡「`db:up` = MySQL」或 `ci`/`dev` 并行三 deps 一律改为总闸语义；注明旧目录可手删、无自动迁移

## 4. 手验与本地 CI

- [x] 4.1 apply 前若旧 `pg_ctl` 仍在跑则先 `pg:down`；手验 `devbox run -- task db:up` 三库就绪；再手验分库 `redis:down` 后 MySQL/PG 仍在
- [x] 4.2 `devbox run -- task ci` 全绿

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2。每个 apply 会话建议只完成 1 个 Task 节。
