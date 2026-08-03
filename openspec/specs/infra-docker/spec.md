# infra-docker Specification

## Purpose

CI/CD Build 层：`build-push.yaml`（Build and Push Container Images）多阶段 Dockerfile、**仅** semver tag `vX.Y.Z`（及 workflow_dispatch）触发 GHCR push、镜像 tag 为去 `v` 的精确版本；废止 main push build 与浮动镜像 tag。

## Requirements

### Requirement: Multi-stage application Dockerfile

仓库 SHALL 提供多阶段 `Dockerfile`：builder 阶段安装生产依赖（不含 dev 组）；runtime 阶段 SHALL 仅包含 `app/`、Python 运行时、生产 `.venv`（或等价）及 `uvicorn` 启动命令。镜像 **SHALL NOT** 包含 MySQL、Redis、tests 或 devbox。

#### Scenario: 镜像不含 tests 目录

- **WHEN** 对构建上下文执行 `docker build` 且 `.dockerignore` 生效
- **THEN** 最终镜像文件系统 SHALL NOT 含 `tests/` 目录

#### Scenario: 默认启动命令为 uvicorn

- **WHEN** 容器无 override CMD 启动
- **THEN** SHALL 监听 `0.0.0.0:8000` 并提供 FastAPI 应用

### Requirement: Build-push workflow naming

Build 层 workflow 文件 SHALL 命名为 `.github/workflows/build-push.yaml`，workflow `name` SHALL 为 `Build and Push Container Images`。

#### Scenario: workflow 文件与 display name

- **WHEN** 查看 `.github/workflows/build-push.yaml`
- **THEN** 首行 `name:` SHALL 为 `Build and Push Container Images`
- **AND** 旧文件 `docker-build.yml` SHALL NOT 存在

### Requirement: Docker build workflow trigger

GitHub Actions SHALL 提供独立 workflow（`build-push.yaml`），**仅**在 **push 匹配 `v[0-9]+.[0-9]+.[0-9]+` 的 git tag** 时自动触发。**SHALL NOT** 在 push 到 `main` 分支、feature 分支 push 或 pull_request 上默认触发镜像 build。workflow MAY 支持 `workflow_dispatch` 手动触发（须输入合法 semver `X.Y.Z`）。

#### Scenario: semver tag 触发 build

- **WHEN** push tag `v1.0.0`
- **THEN** build-push workflow SHALL 运行
- **AND** 镜像 tag SHALL 为 `1.0.0`（不含 `v` 前缀）

#### Scenario: main push 不触发 build

- **WHEN** commit push 到 `main` 且无匹配 semver tag
- **THEN** build-push workflow SHALL NOT 运行

#### Scenario: feature 分支 push 不触发

- **WHEN** 仅 push 到 `feature/*` 且无 tag push
- **THEN** build-push workflow SHALL NOT 自动运行

### Requirement: Release tag semver image tag

build workflow SHALL 从 git tag `vX.Y.Z` 推导镜像 tag：去掉前缀 `v` 得到 `X.Y.Z`，并 **仅** push 该精确 tag 至 GHCR（如 `ghcr.io/<owner>/e-commerce-system:1.0.0`）。**SHALL NOT** push `latest`、`sha-*`、`X.Y`、`X` 等浮动或衍生 tag。

#### Scenario: v1.0.0 tag 映射为 1.0.0 镜像

- **WHEN** push git tag `v1.0.0` 触发 build-push workflow
- **THEN** GHCR SHALL 存在 tag 为 `1.0.0` 的镜像
- **AND** SHALL NOT 存在因该次 build 新 push 的 `latest` tag

#### Scenario: 非标准 tag 不触发 build

- **WHEN** push git tag `v1.0` 或 `v1` 或 `release-foo`
- **THEN** build-push workflow SHALL NOT 运行

#### Scenario: workflow_dispatch 手动 semver

- **WHEN** 通过 workflow_dispatch 触发且输入合法 `version=1.2.3`
- **THEN** build SHALL push 镜像 tag `1.2.3`

### Requirement: GHCR image push

build workflow SHALL 将镜像 push 至 **GHCR**（`ghcr.io/<owner>/e-commerce-system` 或文档约定等价路径）。workflow SHALL 配置 `permissions.packages: write`（或等价）以允许 push。每次成功 build 产生的可拉取 tag SHALL 与当次 release semver 一致（见 Release tag semver image tag requirement）。镜像 repository 路径 **SHALL** 使用小写 owner（如 `${GITHUB_REPOSITORY,,}`），以满足 GHCR 命名约束。

#### Scenario: 构建成功后镜像可拉取

- **WHEN** build-push workflow 成功完成且 tag 为 `v2.1.0`
- **THEN** GHCR SHALL 存在 tag `2.1.0` 的镜像

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
