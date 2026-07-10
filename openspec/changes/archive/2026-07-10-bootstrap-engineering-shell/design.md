## Context

项目处于工程壳阶段：`app/` 与 `tests/` 仅有空占位，无依赖文件、无 CI、无应用入口。本 change 建立后续所有垂直切片的公共底座，并练习 `feature → dev → main` 企业分支流。

约束来自 explore 决策：Python 3.13、devbox（本地工具链）、uv（Python 包）、go-task（CLI 入口）、health 归属 infra（非业务域）。

## Goals / Non-Goals

**Goals:**

- 本地 `devbox shell` 后可通过 `task sync` / `task ci` / `task dev` 完成开发闭环
- 远程 GitHub Actions 与本地 `task ci` 行为等价（ruff + pytest）
- `GET /health` 作为首个可演示、可测试的垂直切片
- design 中固化 CI 触发策略，便于习惯企业工作流

**Non-Goals:**

- MySQL、docker-compose、integration job、Docker CD、业务域实现
- CI 中使用 devbox
- readiness 探针（DB 连通性检查）

## Decisions

### 1. 本地工具链：devbox + uv + go-task

| 组件 | 职责 |
|------|------|
| devbox | OS 级无状态 CLI：Python 3.13、uv、go-task |
| uv | Python 依赖、锁文件、运行 ruff/pytest/uvicorn |
| go-task | 统一入口：`sync`、`ruff`、`test`、`ci`、`dev` |

**理由**：devbox 保证换机可复现 shell 工具链；uv 快且单文件 `pyproject.toml`；task 让本地与 CI 共用同一命令名。

**替代方案**：poetry（更重）；Makefile（Windows 体验差）；CI 也用 devbox（冷启动慢，否决）。

### 2. 本地 vs CI 环境策略

```text
本地：devbox shell → task *
CI：  actions/setup-python 3.13 + astral-sh/setup-uv → task ci
```

有状态服务（MySQL 等）留待后续 change，届时用 docker-compose；本 change 不涉及。

**理由**：行为 parity 通过 `task ci` 统一，而非复制 devbox 到 Runner。

### 3. health 归属 infra，非业务域

```text
app/infra/health/
  router.py      # GET /health
  schemas.py     # HealthResponse
  service.py     # get_health_status()（纯内存，无 IO）
```

**理由**：health 是运维能力，与 user/catalog 等业务限界上下文无关；仍保留 router → service → schemas 分层，作为后续业务域的结构样板。

### 4. Task 命令定义

| Task | 命令（概念） |
|------|-------------|
| `sync` | `uv sync` |
| `ruff` | `uv run ruff check .` |
| `test` | `uv run pytest` |
| `ci` | `ruff` + `test`（顺序） |
| `dev` | `uv run uvicorn app.main:app --reload` |

### 5. 分支与 CI 触发策略

```text
feature/* ──PR──▶ dev ──PR──▶ main（可部署）
```

| 事件 | 触发条件 | CI 动作 |
|------|----------|---------|
| `pull_request` | base = `dev` | `task ci` |
| `push` | branch = `dev` | `task ci`（集成回归） |
| `pull_request` | base = `main` | `task ci` |
| `push` | branch = `main` | `task ci`（未来可加 CD） |

feature 分支直接 push **不强制**跑 CI（节省配额）；合入 dev 前通过 PR 触发。

**理由**：对齐企业「main = 生产线」；dev 作为集成缓冲。

### 6. TDD 实施顺序

tasks.md 严格按 **失败测试 → 实现** 拆分；Apply 时先确认 pytest 红，再写实现至绿。

### 7. Python 与依赖

- Python **3.13**（devbox.json 与 workflow 对齐）
- `uv.lock` **入库**
- 核心依赖：fastapi、uvicorn、pytest、httpx（TestClient）、ruff

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| Windows 上 devbox 体验不稳定 | 优先 WSL；README 注明验证步骤 |
| 本地与 CI Python patch 版本不一致 | devbox 与 workflow 均 pin 3.13.x |
| task ci 绿但 PR CI 红 | workflow 直接调用 `task ci`；DoD 要求远程绿 |
| health 被误当作业务域 | 文档与目录明确 infra/health 定位 |

## Migration Plan

1. 合并到 `dev` 后，后续 feature change 基于 dev 分支开发
2. 无需数据迁移或回滚策略（纯新增工程文件）

## Open Questions

（无。explore 阶段决策已闭合。）
