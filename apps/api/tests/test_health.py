"""헬스체크 엔드포인트 테스트."""

from fastapi.testclient import TestClient

from main import app


def test_health_returns_200() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "valuechain-api"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_openapi_schema_available() -> None:
    """개발 모드에선 /docs 활성화 검증."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "ValueChain AI API"


def test_cors_preflight() -> None:
    """CORS preflight 응답 정상 검증."""
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # preflight는 200 또는 204
    assert response.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in response.headers}
