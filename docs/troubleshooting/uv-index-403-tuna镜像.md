# uv：修改 pyproject 后 sync/run 报 index 403（镜像拒绝）

## 场景

修改 `pyproject.toml`（本例为 `[tool.ruff]` 配置段）后，本地执行 `uv run <cmd>` 或 `uv sync` 报：

```text
Failed to build `e-commerce-system @ file:///.../e-commerce-system`
Failed to resolve requirements from `build-system.requires`
No solution found when resolving: `hatchling`
hint: An index (https://pypi.tuna.tsinghua.edu.cn/simple) returned a 403 Forbidden error.
```

常见触发命令：`uv run ruff format --check`、`uv run alembic ...`、`devbox run -- task ci`（Taskfile 内均为 `uv run`）。

而**改动前** `uv run` 一直正常；`uv lock` 能成功（1ms）；`UV_OFFLINE=1 uv sync` 也能成功；直接 `.venv/bin/ruff ...` 也正常。

## 问题

uv 判定 pyproject 变化后进入"重新评估"路径，需要联网访问 index 做交叉验证，但 index 返回 403。**不是 ruff/alembic 坏了**，而是 `uv run` 在跑命令前要重装 editable 项目包，需拉取 `[build-system]` 的 `hatchling`，联网阶段失败。

## 根因

### 1. uv 的三方一致性模型

uv 维护不变量：**`.venv ≡ uv.lock ≡ pyproject`**（依赖声明相关部分）。

- 每次 `uv run` / `uv sync` 都会校验：uv 把 pyproject 的 **content hash** 记在 `uv.lock` 里；改 pyproject **任何内容**（含 tool 段）→ hash 变 → uv 认为"声明可能变了，需重新评估"。
- **状态一致时** uv 纯本地缓存比对（`Resolved from cache / Checked N packages`），**零网络**——这就是平时 `uv run` 正常、从不联网的原因。

### 2. 只有"重新评估"那一次才联网

pyproject 变化 → 首次重新评估 → 需向 index 取元数据交叉验证 → 走 `UV_INDEX_URL`。状态重新一致后，再 `uv sync` 又是纯缓存、零网络。

**为何报错里出现 `hatchling` 而非 `ruff`？** 本项目 `pyproject.toml` 的 `[build-system]` 使用 `hatchling` 构建 editable 包；重评估时会先装 build 依赖，再执行你请求的 `ruff`/`pytest` 等。

### 3. 403 来自镜像本身，不是代理也不是 uv

`UV_INDEX_URL` 指向 `https://pypi.tuna.tsinghua.edu.cn/simple`（常见来源：`~/.bashrc` 全局 export，或历史 `uv lock` 写入 `uv.lock`），而**该镜像对当前访问返回 403**（实测）：

| 探测 | 结果 |
|------|------|
| tuna 走本地代理 `127.0.0.1:7897` | 403 |
| tuna 直连（绕过代理） | 403 |
| 官方 `https://pypi.org/simple/hatchling/` 走代理 | **200** |
| `uv lock`（缓存命中、未改 pyproject hash） | 成功 |
| `UV_OFFLINE=1 uv sync` | 成功 |
| `.venv/bin/ruff format --check`（绕过 uv） | 成功 |

tuna 对 uv/curl 的请求返回 403（反爬/限流/临时故障，与本地代理、uv 无关）。此前 `uvx black` 也 403——问题**独立于具体 change 存在**，只是"改 pyproject / 触发重评估"时才暴露。2026-08 在 `test-testkit-rename` 本地 CI 阶段再次遇到同一现象。

### 4. 依赖没变，所以 uv.lock 常无解析 diff

`[tool.ruff]` 等 tool 段**不参与依赖解析** → 解析结果不变 → 仅换 tool 段时 `uv lock` 往往无包版本 diff。离线 sync 只需重装**项目自身**（editable 安装，刷新 `.dist-info` 元数据），日志表现为 `Uninstalled 1 package / Installed 1 package`（`e-commerce-system==0.1.0`）。

### 5. 只 export 换源不够：lock 里仍可能锁死 tuna URL

历史 `uv.lock` 中每个包的 `source.registry` 与 `url` 可能全是 `pypi.tuna.tsinghua.edu.cn`。即使 shell 里 `export UV_INDEX_URL=https://pypi.org/simple`，旧 lock 仍记录 tuna 为 registry；**项目级根治应同时**：

1. 固定 devbox/CI 用的 index（见下）
2. `uv lock` 重生成 lock（registry URL 全部迁到官方）
3. `uv sync`

## 解决

### 项目级根治（已采用）

`devbox.json` 固定官方源，团队 `devbox run --` 与 Taskfile 内 `uv run` 不再继承 shell 里的 tuna：

```json
"UV_INDEX_URL": "https://pypi.org/simple"
```

换源并重锁、同步：

```bash
devbox run -- uv lock
devbox run -- uv sync
devbox run -- uv run ruff format --check .   # 验证
```

**已在 devbox shell 内的会话**：改 `devbox.json` 不会热更新 env，需 **退出并重新 `devbox shell`**，或当前 shell 临时 `export UV_INDEX_URL=https://pypi.org/simple`。

### 临时绕过（本地依赖不变、未换 lock 时）

```bash
UV_OFFLINE=1 uv sync
uv run <cmd>
```

或跳过 uv 一致性检查（与 CI 门禁等价，但不验证 editable 项目包元数据）：

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
APP_ENV_FILE=.env.test .venv/bin/python -m pytest
```

### 个人 shell 仍配 tuna 时

```bash
export UV_INDEX_URL=https://pypi.org/simple   # 或 unset UV_INDEX_URL（uv 默认官方 PyPI）
uv lock && uv sync
```

建议检查并注释/删除 `~/.bashrc` 里全局 `UV_INDEX_URL=...tuna...`，避免与 `devbox.json` 冲突（`devbox run` 以 devbox env 为准；裸 `uv` 仍吃 shell）。

### 判别命令

确认 403 来自镜像而非代理/网络：

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.tuna.tsinghua.edu.cn/simple/hatchling/
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/hatchling/
rg 'pypi\.tuna' uv.lock   # 换源后应为 0
```

## 验证

换源 + `uv lock` + `uv sync` 后：

- `devbox run -- uv run ruff format --check .` 正常
- `devbox run -- task ci` 不再在 `format:check` 阶段 403
- `uv.lock` 中 `source.registry` 均为 `https://pypi.org/simple`

GitHub Actions CI 走官方 PyPI，不受本地历史 tuna 配置影响。

## 关键概念

- **uv 三方一致性**：`pyproject.toml`（声明）→ `uv.lock`（锁定解析）→ `.venv`（实际安装）；uv 在 `uv run`/`uv sync` 前自动校验三者对齐
- **content hash**：`uv.lock` 记录 pyproject 内容哈希，用于判断"是否需重新评估"；tool 段改动也改变哈希
- **缓存命中**：状态一致或缓存元数据齐全时，`uv lock`/`uv sync` 可零网络完成
- **`UV_OFFLINE`**：强制纯离线（只信 lock + 本地缓存），不发任何网络请求
- **editable 项目包**：pyproject 变化会触发项目自身重装以刷新元数据，需 `hatchling` 等 build 依赖；不影响第三方 dev 依赖是否已在 `.venv`
- **`devbox.json` env 优先级**：`devbox run --` 注入 `UV_INDEX_URL`；长期 shell 需重进 devbox 才生效

## 关联文件

- `devbox.json` — `UV_INDEX_URL` 项目级 index（`devbox run` 生效）
- `pyproject.toml` — 修改它触发重解析；`[build-system] requires hatchling`
- `uv.lock` — 锁定解析结果与 registry URL；换源后应无 `pypi.tuna` 字样
- 环境变量 `UV_INDEX_URL` — shell 级 index；与 devbox 不一致时裸 `uv` 仍可能走 tuna
- `.venv` — 实际安装，需与 lock 对齐
