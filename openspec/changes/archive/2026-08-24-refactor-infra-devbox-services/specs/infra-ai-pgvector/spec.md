## MODIFIED Requirements

### Requirement: Local PostgreSQL via devbox

系统 SHALL 通过 **devbox postgresql 插件服务**（process-compose 进程名 `postgresql`）提供本地 PostgreSQL（含 **pgvector**）；SHALL 提供 `task pg:up` 与 `task pg:down` 及就绪轮询（`pg_isready`），并确保 dev/test AI 库存在。`pg:up` SHALL NOT 使用独立于 process-compose 的 `pg_ctl start` 作为主路径。`pg:down` SHALL 使用 `devbox services stop postgresql`。

#### Scenario: pg up 后就绪

- **WHEN** 开发者在项目根目录执行 `devbox run -- task pg:up` 且 PostgreSQL 正常启动
- **THEN** 脚本 SHALL 在超时内检测到 `pg_isready` 成功并输出就绪摘要
- **AND** `postgresql` 进程 SHALL 由 process-compose 监督（`devbox services ls` 为 Running）

#### Scenario: pg down 停止服务

- **WHEN** 三库均在跑且开发者执行 `devbox run -- task pg:down`
- **THEN** PostgreSQL 插件服务 SHALL 停止
- **AND** MySQL 与 Redis SHALL 仍可继续运行
