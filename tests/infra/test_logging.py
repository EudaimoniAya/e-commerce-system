"""infra/logging 结构化日志与 request_id middleware 测试（TDD 红阶段）。

本文件仅编写测试用例；loguru 配置、InterceptHandler、request_id middleware、
create_app 工厂均在后续 task 实现。
"""

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class TestSetupLoggingByAppEnv:
    """app_env 推导日志格式与级别（spec: Log format and level derived from app_env）。"""

    def test_development_format_human_readable(self) -> None:
        """development 环境 stderr 人类可读，级别 INFO。"""
        from app.infra.logging.setup import setup_logging

        settings = MagicMock()
        settings.app_env = "development"

        with patch("app.infra.logging.setup.logger") as mock_logger:
            setup_logging(settings)

        calls = mock_logger.add.call_args_list
        assert len(calls) >= 1, "应至少注册 1 个 sink"

        # 终端 sink：serialize 应为 False 或缺失（人类可读）
        stderr_calls = [
            c for c in calls if c.kwargs.get("level") == "INFO" and not c.kwargs.get("serialize")
        ]
        assert len(stderr_calls) >= 1, "development 终端 sink 应为人类可读 (serialize=False) 且 level=INFO"

    def test_test_environment_json_warning_no_file(self) -> None:
        """test 环境终端 JSON、WARNING，不写文件。"""
        from app.infra.logging.setup import setup_logging

        settings = MagicMock()
        settings.app_env = "test"

        with patch("app.infra.logging.setup.logger") as mock_logger:
            setup_logging(settings)

        calls = mock_logger.add.call_args_list
        # 终端 JSON sink（WARNING）
        stderr_calls = [
            c
            for c in calls
            if c.kwargs.get("level") == "WARNING" and c.kwargs.get("serialize") is True
        ]
        assert len(stderr_calls) >= 1, "test 终端 sink 应为 JSON (serialize=True) 且 level=WARNING"

        # 不应注册文件 sink
        file_calls = [
            c
            for c in calls
            if isinstance(c.args[0], str) and "logs/" in str(c.args[0])
        ]
        assert len(file_calls) == 0, "test 环境不应注册文件 sink"

    def test_production_environment_json_info(self) -> None:
        """production 环境终端 JSON、INFO，有文件 sink。"""
        from app.infra.logging.setup import setup_logging

        settings = MagicMock()
        settings.app_env = "production"

        with patch("app.infra.logging.setup.logger") as mock_logger:
            setup_logging(settings)

        calls = mock_logger.add.call_args_list
        # 终端 JSON sink（INFO）
        stderr_calls = [
            c
            for c in calls
            if c.kwargs.get("level") == "INFO" and c.kwargs.get("serialize") is True
        ]
        assert len(stderr_calls) >= 1, "production 终端 sink 应为 JSON (serialize=True) 且 level=INFO"

        # 文件 sink
        file_calls = [
            c
            for c in calls
            if isinstance(c.args[0], str) and str(c.args[0]) == "logs/app.log"
        ]
        assert len(file_calls) >= 1, "production 应注册 logs/app.log 文件 sink"


class TestFileSinkConfig:
    """文件 sink 配置（spec: Local persistent log file）。"""

    def test_file_sink_rotation_and_compression(self) -> None:
        """文件 sink 启用 rotation 和 compression=gz。"""
        from app.infra.logging.setup import setup_logging

        settings = MagicMock()
        settings.app_env = "development"

        with patch("app.infra.logging.setup.logger") as mock_logger:
            setup_logging(settings)

        calls = mock_logger.add.call_args_list
        file_calls = [
            c
            for c in calls
            if isinstance(c.args[0], str) and str(c.args[0]) == "logs/app.log"
        ]
        assert len(file_calls) >= 1, "development 应注册文件 sink"
        fc = file_calls[0]
        assert fc.kwargs.get("rotation") is not None, "文件 sink 应配置 rotation"
        assert fc.kwargs.get("compression") == "gz", "文件 sink 应配置 compression=gz"
        assert fc.kwargs.get("serialize") is True, "文件 sink 应为 JSON 格式"
        assert fc.kwargs.get("enqueue") is True, "文件 sink 应启用 enqueue"

    def test_setup_logging_creates_logs_directory(self) -> None:
        """启动时确保 logs/ 目录存在。"""
        from app.infra.logging.setup import setup_logging

        settings = MagicMock()
        settings.app_env = "development"

        with (
            patch("app.infra.logging.setup.logger"),
            patch("app.infra.logging.setup.Path") as mock_path_cls,
        ):
            setup_logging(settings)
            mock_path_cls.assert_called_once_with("logs")
            mock_path_cls.return_value.mkdir.assert_called_once_with(exist_ok=True)


class TestInterceptHandler:
    """InterceptHandler 统一 stdlib logging 到 loguru（spec: InterceptHandler unifies stdlib logging）。"""

    def test_is_logging_handler_subclass(self) -> None:
        """InterceptHandler 是 logging.Handler 的子类。"""
        from app.infra.logging.setup import InterceptHandler

        assert issubclass(InterceptHandler, logging.Handler), (
            "InterceptHandler 应继承 logging.Handler"
        )

    def test_emit_forwards_to_loguru(self) -> None:
        """emit 将 stdlib LogRecord 转换并交 loguru 处理。"""
        from app.infra.logging.setup import InterceptHandler

        handler = InterceptHandler()
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="GET /health 200",
            args=(),
            exc_info=None,
        )

        with patch("app.infra.logging.setup.logger") as mock_logger:
            handler.emit(record)
        # InterceptHandler 应调用 loguru 方法处理记录
        assert mock_logger.opt.called or mock_logger.log.called, (
            "InterceptHandler.emit 应调用 loguru logger 的 opt 或 log 方法"
        )


class TestRequestIdMiddleware:
    """Request ID middleware（spec: Request ID middleware）。"""

    @pytest.fixture
    def app_with_middleware(self) -> FastAPI:
        """最小 FastAPI app，注册 request_id middleware。"""
        from app.infra.logging.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        return app

    # ── 无客户端 ID → 服务端生成 ──

    @pytest.mark.asyncio
    async def test_no_client_id_generates_request_id(
        self, app_with_middleware: FastAPI,
    ) -> None:
        """无 X-Request-ID 时服务端生成 UUID4，响应头回传。"""
        transport = ASGITransport(app=app_with_middleware)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/ping")

        assert response.status_code == 200
        assert "x-request-id" in response.headers
        request_id = response.headers["x-request-id"]
        assert request_id != "", "生成 request_id 不应为空"
        try:
            uuid.UUID(request_id)
        except ValueError:
            pytest.fail(f"生成 request_id 不是有效 UUID: {request_id!r}")

    # ── 客户端透传合法 ID ──

    @pytest.mark.asyncio
    async def test_client_provided_id_passed_through(
        self, app_with_middleware: FastAPI,
    ) -> None:
        """客户端携带合法 X-Request-ID 时透传。"""
        client_id = "client-req-001"
        transport = ASGITransport(app=app_with_middleware)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-Request-ID": client_id},
        ) as client:
            response = await client.get("/ping")

        assert response.status_code == 200
        assert response.headers["x-request-id"] == client_id

    # ── 响应头始终包含 X-Request-ID ──

    @pytest.mark.asyncio
    async def test_response_always_has_request_id_header(
        self, app_with_middleware: FastAPI,
    ) -> None:
        """任意请求的响应头都包含 X-Request-ID。"""
        transport = ASGITransport(app=app_with_middleware)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/ping")

        assert "x-request-id" in response.headers
        assert response.headers["x-request-id"] != ""


class TestRequestIdContextVar:
    """request_id ContextVar 与 get_request_id。"""

    def test_get_request_id_returns_ctx_var_value(self) -> None:
        """get_request_id 返回 ContextVar 当前值。"""
        from app.infra.logging.middleware import REQUEST_ID_CTX_VAR, get_request_id

        test_id = "test-id-abc123"
        token = REQUEST_ID_CTX_VAR.set(test_id)
        try:
            assert get_request_id() == test_id
        finally:
            REQUEST_ID_CTX_VAR.reset(token)

    def test_get_request_id_default_is_empty(self) -> None:
        """未设置时 get_request_id 返回空字符串或合理默认值。"""
        from app.infra.logging.middleware import get_request_id

        result = get_request_id()
        # 默认值应为空字符串或 "-"
        assert result == "" or result == "-", f"默认值不应为非空标识: {result!r}"


class TestIsValidRequestId:
    """X-Request-ID 合法性校验函数。"""

    def _call(self, value: str | None) -> bool:
        from app.infra.logging.middleware import is_valid_request_id

        return is_valid_request_id(value)  # type: ignore[arg-type]

    def test_valid_uuid_accepted(self) -> None:
        """UUID4 格式通过校验。"""
        assert self._call(str(uuid.uuid4())) is True

    def test_alphanumeric_dash_dot_underscore_accepted(self) -> None:
        """字母数字 + 短横线 + 点 + 下划线通过校验（代理/网关常见格式）。"""
        valid = ["abc-123", "req.test_001", "A", "A" * 128]
        for rid in valid:
            assert self._call(rid) is True, f"应接受: {rid!r}"

    def test_empty_rejected(self) -> None:
        """空字符串不合法。"""
        assert self._call("") is False

    def test_whitespace_only_rejected(self) -> None:
        """纯空白字符串不合法。"""
        assert self._call("   ") is False

    def test_too_long_rejected(self) -> None:
        """超过 128 字符不合法。"""
        assert self._call("a" * 129) is False

    def test_special_chars_rejected(self) -> None:
        """含空白或非法字符（如 @、空格）不合法。"""
        assert self._call("bad@id") is False
        assert self._call("id with spaces") is False

    def test_none_rejected(self) -> None:
        """None 不合法。"""
        assert self._call(None) is False

