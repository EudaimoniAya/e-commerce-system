## Why

项目当前仅有空目录占位，缺少可运行的应用入口、开发工具链、测试与 CI 门禁。需要在编写任何业务域（user/catalog/ordering）之前，搭建统一的工程底座，使后续垂直切片能遵循 SDD + TDD 流程，并通过 `feature → dev → main` 分支策略练习企业级工作流。

## What Changes

- 引入 **devbox** 管理 OS 级工具链（Python 3.13、uv、go-task 等），本地开发通过 shell 进入统一环境
- 使用 **uv** 管理 Python 依赖与工具（ruff、pytest 等），`uv.lock` 入库保证可复现
- 使用 **go-task** 封装 CLI：`sync`、`ruff`、`test`、`ci`、`dev`
- 添加 FastAPI 应用入口 `app/main.py` 与 **infra/health** 运维能力（`GET /health` 冒烟端点，与业务无关）
- 添加 GitHub Actions CI workflow，远程执行与本地 `task ci` 等价的 lint + test
- 在 design 中定义 **CI 触发策略**（PR → dev、push dev、PR dev → main、push main）
- 添加 `.env.example` 与 README 中的开发/分支/DoD 说明

## Non-goals

- 不接入 MySQL 或任何数据库
- 不添加 docker-compose / 容器编排
- 不添加 integration 测试 job 或 pytest integration marker 体系
- 不构建 Docker 镜像或 CD 部署
- 不实现任何业务域（user、catalog、ordering 等）
- 不在 CI 中使用 devbox（本地 devbox + CI 直接安装 uv 即可）

## Capabilities

### New Capabilities

- `infra-health`: 运维向存活探针 `GET /health`，返回固定 JSON，用于冒烟测试与后续部署探针

### Modified Capabilities

（无。`openspec/specs/` 尚无既有规格。）

## Impact

- **业务域**: `infra`（health 子模块，非业务限界上下文）
- **新增文件**: `devbox.json`、`pyproject.toml`、`uv.lock`、`Taskfile.yml`、`app/main.py`、`app/infra/health/`、`tests/health/`、`.github/workflows/ci.yml`、`.env.example`
- **文档**: `README.md` 开发指南；`docs/architecture.md` 目录结构可随实现微调
- **分支策略**: feature 分支 PR 合入 `dev`；稳定后 `dev` PR 合入 `main`（main 为可部署线）
- **DoD**: 本地 `task ci` 全绿 → push 后远程 CI 全绿 → 更新文档 → archive 归档
