## Context

电商 MVP（user / catalog / ordering + infra 横切）已在 `dev` 交付；`.github/workflows/ci.yml` 为单一 `ci` job（ruff + test-import + 全量 pytest），无 uv cache、无测试报告 artifact、无域并行。架构文档 §8.3 规划「合并 main / tag → Docker 镜像构建」，仓库尚无 `Dockerfile`。项目采用 gitflow（`feature/* → dev → main`），计划以 **v1.0.0** 标记电商底座首次 release；v1.x.0 为底座完善；v2.0.0 为 AI 平台。

约束：

- GitHub Actions `uses:` 须锁定 commit SHA（`.cursor/rules/github-actions-pinning.mdc`）
- 本地 MySQL/Redis 仍用 devbox（ADR-002）；**不** 用 docker-compose 替代
- integration 测试须 `AsyncClient`；CI 仍用 `services.mysql` + `services.redis`
- DB/Redis 相关本地命令须 `devbox run --` 包装
- app 镜像 **不含** MySQL/Redis/tests；运行时通过 `DATABASE_URL` / `REDIS_URL` 连接外置服务

## Goals / Non-Goals

**Goals:**

- CI：lint 独立 job；test matrix 按域并行；uv cache；`workflow_dispatch` 域筛选
- Allure：`allure-pytest`；`reports/` 本地目录（gitignore）；`test:reports` / `latest:report` Task；CI 每 matrix job upload artifact
- Allure 层级：`@allure.epic`（域）+ `@allure.feature`（场景）+ `@allure.title`（Story，从 docstring/测试名迁移）
- Taskfile 域测试：`test:user` / `test:catalog` / `test:ordering` / `test:infra` / `test:unit`（pytest 路径筛选）
- Docker：多阶段 Dockerfile；`docker-build.yml`；push **GHCR**；触发 **main push + v* tag**
- 文档：README、architecture §8.3、semver 策略（v1.0.0 / v1.x / v2.0）

**Non-Goals:**

- CD（SSH、docker-compose 部署）→ `infra-cd-compose`
- K8s、GitOps、cosign、CodeQL、Dependabot
- PR 默认 build 镜像；镜像内 MySQL/Redis
- 新增 pytest domain marker（与路径筛选重复）
- `scripts/*_curl_smoke.sh` 类 bash HTTP 烟雾脚本（与 integration 重复；见 §0 清理）

## Decisions

### 1. CI job 结构：lint + test matrix（非单 job）

**选择**：

```text
jobs:
  lint:     ruff + check-test-imports（无 services；**须先安装 ripgrep**，见 §7.1a）
  test:     matrix.domain ∈ {user, catalog, ordering, infra, unit}
            needs: []  # 与 lint 并行
            services: mysql + redis → migrate → pytest --alluredir
            upload-artifact: allure-results-${{ matrix.domain }}
```

**理由**：域失败定位清晰；lint 不等待 DB；与 DevOps Validate 分层一致。

**`check-test-imports` 与 `rg`**：`scripts/check_no_test_cross_imports.sh` 依赖 **ripgrep**（`rg`），非 POSIX `grep`。Implement §7 时须在 **CI lint job** 显式 `apt install ripgrep`，并在 **`devbox.json`** 增加 `ripgrep` 包，避免本地 / CI 出现 `Command 'rg' not found`（详见 `infra-ci` spec、`tasks.md` §7.1a）。

**备选**：保留单 job + 仅 workflow_dispatch 筛选（反馈慢，否决）。

### 2. 域筛选：pytest 路径（非 marker）

| matrix / task | pytest 路径 |
|---------------|-------------|
| user | `tests/user tests/unit/user` |
| catalog | `tests/catalog tests/unit/catalog` |
| ordering | `tests/ordering` |
| infra | `tests/infra tests/ops` |
| unit | `tests/unit` |

`workflow_dispatch` 输入 `domain`：`all` 时 lint + 全 matrix；单域时仅对应 matrix 行。

**理由**：目录已是域边界（test-architecture）；避免 252 用例加 `@pytest.mark.user`。

### 3. uv cache

**选择**：`actions/cache`，path `~/.cache/uv`，key `uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}`。

**理由**：`uv sync` 为每个 matrix job 重复执行；lock 变更自动 bust cache。

### 4. Allure 本地与 CI

| 项 | 约定 |
|----|------|
| 原始结果 | `reports/allure-results/` |
| HTML 报告 | `reports/allure-report/` |
| gitignore | `reports/` |
| `test:reports` | deps `db:up` + `redis:up` → pytest `--alluredir=reports/allure-results` → `allure generate -o reports/allure-report --clean` |
| `latest:report` | 检查 `reports/allure-report` 存在 → `allure open reports/allure-report` |
| CI | 每 matrix job `--alluredir=allure-results` → artifact `allure-results-<domain>`（保留 14 天） |
| Allure CLI | 本地由开发者安装（文档说明）；CI job 仅 upload results，可选 `allure generate` 为第二 artifact |

**理由**：用户熟悉 Allure；本地 `open` 已 generate 的 HTML；CI 不依赖在线 Allure 服务。

### 5. Allure 装饰器层级

**选择**：每个 integration/unit Case 添加：

```python
@allure.epic("user")              # 域：user | catalog | ordering | infra | ops | unit
@allure.feature("sms_register")   # 场景：对齐 test 模块主题
@allure.title("SMS 注册成功返回 201")  # 从 docstring 或函数名 cv
```

Epic/Feature 映射表（apply 参考）：

| 目录 | epic | feature 默认 |
|------|------|--------------|
| `tests/user/test_sms_register.py` | user | sms_register |
| `tests/catalog/test_create_product.py` | catalog | create_product |
| `tests/ordering/test_cart_checkout.py` | ordering | cart_checkout |
| `tests/infra/test_pagination.py` | infra | pagination |
| `tests/ops/test_readiness.py` | ops | readiness |
| `tests/unit/user/test_phone.py` | unit | phone |

**备选**：conftest 自动 epic（减少重复但 feature 粒度粗）→ 与用户「装饰器 + 域场景对齐」偏好不符，否决。

### 6. 多阶段 Dockerfile

**选择**：

```dockerfile
# stage builder: python:3.13-slim + uv → uv sync --no-dev → .venv
# stage runtime:  COPY app/ + .venv → ENV PATH → EXPOSE 8000
# CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`.dockerignore`：`tests/`、`.venv`、`mysql-data/`、`reports/`、`.git`、`.env*` 等。

**理由**：镜像仅 runnable API；migrate 在 deploy 阶段执行（`infra-cd-compose`）。

**备选**：单阶段（镜像过大，否决）。

### 7. 镜像 registry 与触发

**选择**：

- Registry：**GHCR** `ghcr.io/<github_owner>/e-commerce-system`
- 触发：`push` to `main`；`push` tags `v*`
- Tags：`v1.0.0`（semver）、`sha-<short>`（可追溯）、`latest`（仅 main 最新）
- Auth：`GITHUB_TOKEN` + `packages: write`
- Build 后烟雾：容器内 `curl -f http://127.0.0.1:8000/health`（无需 DB 即可 200）

**理由**：代码在 GitHub；与 Actions 权限一体；用户已确认非 Docker Hub。

**备选**：Docker Hub（需额外 secret，否决）。

### 8. semver 与 release 关系

| Tag | 含义 |
|-----|------|
| v1.0.0 | 电商底座 MVP + 本 change 合入 main 后的首次 release |
| v1.x.0 | 底座完善（engagement、infra-cd-compose 等） |
| v2.0.0 | AI 平台阶段 |

本 change 完成后，`dev → main` PR 合入并打 `v1.0.0` tag 触发首次镜像 build。

### 9. `task ci` 与 CI workflow 关系

**选择**：本地 `task ci` 仍为 **全量** ruff + test-import + pytest（与现有一致）；域筛选仅 **Taskfile 子命令** 与 **GitHub matrix**。不在本地 `task ci` 内拆 matrix。

**理由**：开发者本地一次验证全绿；CI 负责并行加速。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| matrix 5 路并行消耗 Actions 分钟 | 可接受；个人项目；workflow_dispatch 单域可省配额 |
| Allure 装饰器改动 252 用例 diff 大 | tasks 按域分批（user → catalog → ordering → infra/ops/unit） |
| 本地无 Allure CLI 时 `test:reports` generate 失败 | README 文档安装；或 task 检测 CLI 存在性并提示 |
| GHCR 首次 push 需 repo Packages 权限 | workflow `permissions: packages: write` |
| 镜像无 DB 时 `/health/ready` 503 | build 烟雾仅用 `/health`；readiness 留给 compose deploy |

## Migration Plan

1. feature/infra-ci-docker 从 dev 切出 → apply tasks → `devbox run -- task ci` 全绿
2. workflow_dispatch 验证单域 + 全 matrix
3. merge dev → 合 main PR → tag `v1.0.0` → 验证 docker-build workflow
4. 回滚：revert workflow/Dockerfile；旧 CI 单 job 可恢复

## Open Questions

- （已关闭）Registry：GHCR ✓
- （已关闭）Build 触发：main + v* tag ✓
- Allure CLI 是否加入 devbox packages：apply 时评估（可选 `allure2` 若 devbox 有包，否则文档安装）
