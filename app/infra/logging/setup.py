"""loguru 结构化日志配置：setup_logging + InterceptHandler。"""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.infra.config import Settings


class InterceptHandler(logging.Handler):
    """将 stdlib logging 的 LogRecord 转接至 loguru。

    使 uvicorn、SQLAlchemy 等使用 stdlib logging 的库统一输出经 loguru sink，
    全进程日志格式一致。
    """

    def emit(self, record: logging.LogRecord) -> None:
        """接收 stdlib LogRecord，转为 loguru 调用。"""
        # 映射 level name → loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        # 从调用栈向上跳过 InterceptHandler + logging 自身，定位真实 caller
        frame: logging.FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(settings: "Settings") -> None:
    """根据 Settings.app_env 配置 loguru sink 与 InterceptHandler。

    ┌─────────────┬──────────────────────┬──────────────┬──────────────────┐
    │ app_env     │ stderr               │ stderr level │ logs/app.log     │
    ├─────────────┼──────────────────────┼──────────────┼──────────────────┤
    │ development │ 人类可读              │ INFO         │ JSON rotation+gz │
    │ test        │ JSON (serialize=True) │ WARNING      │ 不启用           │
    │ production  │ JSON (serialize=True) │ INFO         │ JSON rotation+gz │
    └─────────────┴──────────────────────┴──────────────┴──────────────────┘
    """
    logger.remove()

    app_env = settings.app_env

    # ── stderr sink ──────────────────────────────────────────────
    if app_env == "development":
        logger.add(
            sys.stderr,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {extra[request_id]} | {message}"
            ),
            level="INFO",
            serialize=False,
        )
    elif app_env == "test":
        logger.add(
            sys.stderr,
            level="WARNING",
            serialize=True,
        )
    elif app_env == "production":
        logger.add(
            sys.stderr,
            level="INFO",
            serialize=True,
        )

    # ── 文件 sink（dev + prod） ──────────────────────────────────
    if app_env in ("development", "production"):
        Path("logs").mkdir(exist_ok=True)
        logger.add(
            "logs/app.log",
            rotation="10 MB",
            compression="gz",
            serialize=True,
            level="INFO",
            enqueue=True,
        )

    # ── InterceptHandler：stdlib → loguru ────────────────────────
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # ── 全局默认 extra（middleware 通过 contextualize 按请求覆盖）──
    logger.configure(extra={"request_id": "-"})
