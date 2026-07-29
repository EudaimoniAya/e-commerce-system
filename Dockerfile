# 多阶段 Dockerfile：仅 FastAPI app + 生产依赖（不含 MySQL/Redis/tests/devbox）
# 规范见 openspec/changes/infra-ci-docker/design.md §6

# ── builder：编译期安装依赖 ──────────────────────────────────────────
FROM python:3.13-slim AS builder
# 升级系统包以修复已知 CVE，随后清理 apt cache 以控制镜像体积
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# 先仅复制依赖声明文件，利用 Docker layer cache——依赖未变时跳过重装
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 再复制源码并安装项目本身（非 editable）
COPY app/ app/
RUN uv sync --frozen --no-dev

# ── runtime：仅运行时文件 ────────────────────────────────────────────
FROM python:3.13-slim
# 升级系统包以修复已知 CVE，随后清理 apt cache 以控制镜像体积
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# 运行时须外置 MySQL + Redis，通过环境变量注入：
#   DATABASE_URL  mysql+asyncmy://user:pass@host:3306/dbname
#   REDIS_URL     redis://host:6379/0
#   JWT_SECRET_KEY  (≥ 32 字节)
# 本地 deploy 见 openspec/changes/infra-cd-compose（后续 change）
