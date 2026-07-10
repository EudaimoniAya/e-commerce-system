"""infra/health 存活探针端点测试（TDD 红阶段）。"""


def test_health_returns_200_with_ok_status(client) -> None:
    """GET /health 在服务正常时返回 200 与 {"status": "ok"}。"""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_content_type_is_json(client) -> None:
    """GET /health 响应 Content-Type 包含 application/json。"""
    response = client.get("/health")

    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type
