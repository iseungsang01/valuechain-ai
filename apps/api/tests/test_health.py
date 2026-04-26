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


def test_cors_allows_vercel_production_domain() -> None:
    """Production vercel 도메인은 정확 매칭으로 허용."""
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://contest2-web.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == (
        "https://contest2-web.vercel.app"
    )


def test_cors_allows_vercel_preview_via_regex() -> None:
    """Vercel preview/branch 도메인은 정규식으로 자동 허용."""
    client = TestClient(app)
    preview_origin = "https://contest2-web-git-feature-foo-iseungsang01.vercel.app"
    response = client.options(
        "/api/health",
        headers={
            "Origin": preview_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == preview_origin


def test_cors_blocks_unknown_origin() -> None:
    """허용 목록/정규식에 없는 도메인은 차단."""
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS 차단 시 ACAO 헤더 미포함 또는 다른 값
    acao = response.headers.get("access-control-allow-origin")
    assert acao != "https://evil.example.com"
