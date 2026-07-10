# e-commerce-system

AI 赋能电商个人练习项目。当前处于 **工程壳** 阶段：可运行的 FastAPI 入口、开发工具链、测试与 CI 门禁已就绪。

## 前置条件

- [devbox](https://www.jetify.com/devbox)（推荐在 **WSL2** 下使用）
- Git

本地工具链由 devbox 提供：Python 3.13、uv、go-task。

## 快速开始

```bash
# 进入 devbox 环境
devbox shell

# 安装 Python 依赖
task sync

# 运行本地 CI（ruff + pytest）
task ci

# 启动开发服务器
task dev
```

开发服务器默认 `http://127.0.0.1:8000`。存活探针：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

## Task 命令

| 命令 | 说明 |
|------|------|
| `task sync` | `uv sync`，同步 Python 依赖 |
| `task ruff` | 运行 ruff lint |
| `task test` | 运行 pytest |
| `task ci` | 本地 CI：`ruff` + `test` |
| `task dev` | `uvicorn app.main:app --reload` |

本地与远程 CI 行为一致：均执行 `task ci`。

## 分支工作流

```text
feature/* ──PR──▶ dev ──PR──▶ main（可部署线）
```

| 场景 | 说明 |
|------|------|
| feature 分支开发 | 从 `dev` 切出，本地 `task ci` 通过后提 PR |
| 合入 dev | PR → `dev` 触发 GitHub Actions CI |
| 合入 main | `dev` → `main` PR，CI 通过后可部署 |

feature 分支直接 push **不**触发远程 CI（节省配额）；合入前通过 PR 验证。

## CI

Workflow：`.github/workflows/ci.yml`

| 事件 | 分支 |
|------|------|
| `pull_request` | `dev`, `main` |
| `push` | `dev`, `main` |

GitHub Actions 使用 **commit SHA** 锁定 action 版本（见 `.cursor/rules/github-actions-pinning.mdc`）。

## Definition of Done（DoD）

单个 OpenSpec change 完成标准：

1. 本地 `task ci` 全绿
2. push 后远程 GitHub Actions 全绿
3. 文档已更新（README、architecture 等）
4. 使用 `/opsx:archive` 归档 change

## 文档

- [架构设计](docs/architecture.md)
- [OpenSpec 变更](openspec/changes/)
