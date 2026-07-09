## 1. 工具链骨架

- [x] 1.1 创建 `devbox.json`（Python 3.13、uv、go-task）与 `pyproject.toml`（fastapi、uvicorn、pytest、httpx、ruff），执行 `uv sync` 生成并提交 `uv.lock`
- [x] 1.2 创建 `Taskfile.yml`，定义 `sync`、`ruff`、`test`、`ci`（ruff + test）、`dev` 任务

## 2. TDD — 失败测试（红）

- [ ] 2.1 按 `specs/infra-health/spec.md` 编写 `tests/health/test_health.py` 及 pytest fixture（TestClient）；**不编写** `app/main.py` 与 `app/infra/health/` 实现
- [ ] 2.2 运行 `task test` 确认测试失败（红），记录预期失败原因（如 ImportError / 404）

## 3. TDD — 实现（绿）

- [ ] 3.1 实现 `app/infra/health/`（schemas、service、router）与 `app/main.py` 挂载路由，使 `task test` 通过（绿）
- [ ] 3.2 运行 `task ci` 确认本地 lint + test 全绿

## 4. 远程 CI

- [ ] 4.1 创建 `.github/workflows/ci.yml`，按 design 中 CI 触发策略（PR→dev、push dev、PR→main、push main）执行 `task ci`
- [ ] 4.2 push 到远程并确认 GitHub Actions 全绿

## 5. 文档与 DoD

- [ ] 5.1 添加 `.env.example` 与 `README.md`（devbox 用法、task 命令、feature→dev→main 分支流、DoD 说明）
- [ ] 5.2 按需更新 `docs/architecture.md` 目录结构；确认 DoD 满足后准备 archive

> **Apply 约定**：严格 TDD，§2 完成前不得开始 §3；每个 apply 会话建议只完成 1–2 个 task。
