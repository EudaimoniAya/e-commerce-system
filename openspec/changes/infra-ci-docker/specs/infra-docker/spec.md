# infra-docker

## Purpose

Build 层：多阶段 Docker 镜像（仅 FastAPI app + 生产依赖），push 至 GHCR；在 push `main` 或 semver tag `v*` 时触发构建与 `/health` 烟雾验证。

## ADDED Requirements

### Requirement: Multi-stage application Dockerfile

仓库 SHALL 提供多阶段 `Dockerfile`：builder 阶段安装生产依赖（不含 dev 组）；runtime 阶段 SHALL 仅包含 `app/`、Python 运行时、生产 `.venv`（或等价）及 `uvicorn` 启动命令。镜像 **SHALL NOT** 包含 MySQL、Redis、tests 或 devbox。

#### Scenario: 镜像不含 tests 目录

- **WHEN** 对构建上下文执行 `docker build` 且 `.dockerignore` 生效
- **THEN** 最终镜像文件系统 SHALL NOT 含 `tests/` 目录

#### Scenario: 默认启动命令为 uvicorn

- **WHEN** 容器无 override CMD 启动
- **THEN** SHALL 监听 `0.0.0.0:8000` 并提供 FastAPI 应用

### Requirement: Docker build workflow trigger

GitHub Actions SHALL 提供独立 workflow（如 `docker-build.yml`），在 **push 到 `main` 分支** 或 **push 匹配 `v*` 的 git tag** 时触发。**SHALL NOT** 在 feature 分支 push 或 pull_request 上默认触发镜像 build。

#### Scenario: main push 触发 build

- **WHEN** commit push 到 `main`
- **THEN** docker-build workflow SHALL 运行

#### Scenario: semver tag 触发 build

- **WHEN** push tag `v1.0.0`
- **THEN** docker-build workflow SHALL 运行且镜像 tag SHALL 含 `v1.0.0`

#### Scenario: feature 分支 push 不触发

- **WHEN** 仅 push 到 `feature/infra-ci-docker` 且无 PR 到 main
- **THEN** docker-build workflow SHALL NOT 自动运行（除非 workflow_dispatch 手动触发，若实现）

### Requirement: GHCR image push

build workflow SHALL 将镜像 push 至 **GHCR**（`ghcr.io/<owner>/e-commerce-system` 或文档约定等价路径）。workflow SHALL 配置 `permissions.packages: write`（或等价）以允许 push。

#### Scenario: 构建成功后镜像可拉取

- **WHEN** docker-build workflow 成功完成
- **THEN** GHCR SHALL 存在对应 tag 的镜像（如 `latest` 与 git sha 或 semver tag）

### Requirement: Container health smoke after build

build workflow SHALL 在 push 前对本地构建的镜像运行容器，并对 `GET /health` 执行请求，期望 HTTP **200** 且 body 含 `"status":"ok"`（或等价）。**SHALL NOT** 要求 `/health/ready` 在 build job 中返回 200（因无 MySQL/Redis sidecar）。

#### Scenario: health 烟雾无需数据库

- **WHEN** build job 启动仅 app 容器（无 DATABASE_URL 指向可达 MySQL 亦可，若 Settings 允许启动）
- **THEN** `GET /health` SHALL 返回 200

#### Scenario: ready 不在 build 烟雾范围

- **WHEN** build 烟雾仅检查 `/health`
- **THEN** workflow 文档或注释 SHALL 说明 `/health/ready` 由 deploy change（compose）验证

### Requirement: Runtime external dependencies via environment

容器运行时 SHALL 通过环境变量 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET_KEY` 连接外置 MySQL 与 Redis；与本地 `.env.example` 契约一致。镜像本身 **SHALL NOT** 捆绑数据库或 Redis 进程。

#### Scenario: 文档说明外置依赖

- **WHEN** 阅读 README Docker 小节
- **THEN** SHALL 说明 deploy 须外置 MySQL/Redis（如后续 docker-compose change）
