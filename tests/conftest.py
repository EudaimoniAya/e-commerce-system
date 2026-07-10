"""pytest 公共 fixture。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient，用于 HTTP 端点测试。"""
    with TestClient(app) as test_client:
        yield test_client
