# uv：修改 pyproject 后 sync/run 报 index 403（镜像拒绝）

## 场景

修改 `pyproject.toml`（本例为 `[tool.ruff]` 配置段）后，本地执行 `uv run <cmd>` 或 `uv sync` 报：

```text
An index URL (https://pypi.tuna.tsinghua.edu.cn/simple) returned a 403 Forbidden error.
This could indicate lack of valid authentication credentials, or the package may not exist on this index.
```

而**改动前** `uv run` 一直正常；`uv lock` 能成功（1ms）；`UV_OFFLINE=1 uv sync` 也能成功。

## 问题

uv 判定 pyproject 变化后进入"重新评估"路径，需要联网访问 index 做交叉验证，但 index 返回 403。

## 根因

### 1. uv 的三方一致性模型

uv 维护不变量：**`.venv ≡ uv.lock ≡ pyproject`**（依赖声明相关部分）。

- 每次 `uv run` / `uv sync` 都会校验：uv 把 pyproject 的 **content hash** 记在 `uv.lock` 里；改 pyproject **任何内容**（含 tool 段）→ hash 变 → uv 认为"声明可能变了，需重新评估"。
- **状态一致时** uv 纯本地缓存比对（`Resolved from cache / Checked N packages`），**零网络**——这就是平时 `uv run` 正常、从不联网的原因。

### 2. 只有"重新评估"那一次才联网

pyproject 变化 → 首次重新评估 → 需向 index 取元数据交叉验证 → 走 `UV_INDEX_URL`。状态重新一致后，再 `uv sync` 又是纯缓存、零网络。

### 3. 403 来自镜像本身，不是代理也不是 uv

`UV_INDEX_URL` 指向 `https://pypi.tuna.tsinghua.edu.cn/simple`，而**该镜像对当前访问返回 403**（实测）：

| 探测 | 结果 |
|------|------|
| tuna 走本地代理 `127.0.0.1:7897` | 403 |
| tuna 直连（绕过代理） | 403 |
| 官方 `https://pypi.org/simple/ruff/` 走代理 | **200** |
| `uv lock`（缓存命中） | 成功 |
| `UV_OFFLINE=1 uv sync` | 成功 |

tuna 对 uv/curl 的请求返回 403（反爬/限流/临时故障，与本地代理、uv 无关）。此前 `uvx black` 也 403——问题**独立于具体 change 存在**，只是"改 pyproject 触发 uv 联网"时才暴露。

### 4. 依赖没变，所以 uv.lock 无 diff

`[tool.ruff]` 等 tool 段**不参与依赖解析** → 解析结果不变 → `uv.lock` 内容不变。离线 sync 只需重装**项目自身**（editable 安装，刷新 `.dist-info` 元数据），日志表现为 `Uninstalled 1 package / Installed 1 package`（`e-commerce-system==0.1.0`）。

## 解决

- **立即（本地依赖不变时）**：

  ```bash
  UV_OFFLINE=1 uv sync
  ```

- **根治（换源）**：官方源走代理可用：

  ```bash
  export UV_INDEX_URL=https://pypi.org/simple   # 或 unset UV_INDEX_URL（uv 默认官方 PyPI）
  ```

- **判别命令**（确认 403 来自镜像而非代理/网络）：

  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" https://pypi.tuna.tsinghua.edu.cn/simple/ruff/
  curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/simple/ruff/
  ```

## 验证

换源后改 pyproject → `uv sync` 正常（不再 403）；`uv run <cmd>` 恢复。CI 走 GitHub Actions 网络，不受本地镜像配置影响。

## 关键概念

- **uv 三方一致性**：`pyproject.toml`（声明）→ `uv.lock`（锁定解析）→ `.venv`（实际安装）；uv 在 `uv run`/`uv sync` 前自动校验三者对齐
- **content hash**：`uv.lock` 记录 pyproject 内容哈希，用于判断"是否需重新评估"；tool 段改动也改变哈希
- **缓存命中**：状态一致或缓存元数据齐全时，`uv lock`/`uv sync` 可零网络完成
- **`UV_OFFLINE`**：强制纯离线（只信 lock + 本地缓存），不发任何网络请求
- **editable 项目包**：pyproject 变化会触发项目自身重装以刷新元数据，不影响其他依赖

## 关联文件

- `pyproject.toml` — 修改它触发重解析
- `uv.lock` — 锁定解析结果（tool 段变化时无 diff）
- 环境变量 `UV_INDEX_URL` — index 地址；指向 403 镜像时所有联网解析失败
- `.venv` — 实际安装，需与 lock 对齐
