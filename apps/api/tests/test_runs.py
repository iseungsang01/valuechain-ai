"""POST /api/runs 엔드포인트 검증 (T3.1).

- RunCreateRequest 검증 (sector 화이트리스트, target_quarter regex)
- RunCreateResponse 형식 (run_id UUID, stream_url 상대경로)
- RunStore 등록 확인
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.runs import InMemoryRunStore, get_run_store
from main import app


def _fresh_store() -> InMemoryRunStore:
    """테스트 격리용 - 매 테스트마다 새 InMemoryRunStore."""
    store = InMemoryRunStore()
    app.dependency_overrides[get_run_store] = lambda: store
    return store


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_post_runs_creates_record_and_returns_stream_url() -> None:
    store = _fresh_store()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs",
            json={
                "sector": "memory_semiconductor",
                "target_quarter": "2024Q3",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert "run_id" in body
        assert "stream_url" in body
        assert body["stream_url"] == f"/api/runs/{body['run_id']}/stream"

        # RunStore 에 등록 확인
        record = store.get(body["run_id"])
        assert record is not None
        assert record.sector == "memory_semiconductor"
        assert record.target_quarter == "2024Q3"
        assert record.is_backtest is False
        assert record.status == "pending"
    finally:
        _clear_overrides()


def test_post_runs_rejects_invalid_sector() -> None:
    _fresh_store()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs",
            json={"sector": "unknown_sector", "target_quarter": "2024Q3"},
        )
        # Pydantic Literal 검증 → 422
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_post_runs_rejects_malformed_quarter() -> None:
    _fresh_store()
    try:
        client = TestClient(app)
        for bad_quarter in ["2024-Q3", "Q3-2024", "2024Q5", "24Q3", ""]:
            response = client.post(
                "/api/runs",
                json={
                    "sector": "memory_semiconductor",
                    "target_quarter": bad_quarter,
                },
            )
            assert response.status_code == 422, f"expected 422 for {bad_quarter!r}"
    finally:
        _clear_overrides()


def test_post_runs_accepts_backtest_with_as_of_date() -> None:
    store = _fresh_store()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs",
            json={
                "sector": "memory_semiconductor",
                "target_quarter": "2024Q3",
                "is_backtest": True,
                "as_of_date": "2024-09-30T23:59:59+00:00",
            },
        )
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        record = store.get(run_id)
        assert record is not None
        assert record.is_backtest is True
        assert record.as_of_date.year == 2024
        assert record.as_of_date.month == 9
    finally:
        _clear_overrides()


def test_post_runs_rejects_extra_fields() -> None:
    _fresh_store()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/runs",
            json={
                "sector": "memory_semiconductor",
                "target_quarter": "2024Q3",
                "malicious_field": "boom",
            },
        )
        # ConfigDict(extra="forbid") → 422
        assert response.status_code == 422
    finally:
        _clear_overrides()


def test_get_stream_returns_404_for_unknown_run_id() -> None:
    _fresh_store()
    try:
        client = TestClient(app)
        # SSE 엔드포인트는 stream=True 필요 없이도 첫 응답으로 404 가능
        response = client.get("/api/runs/non-existent-id/stream")
        assert response.status_code == 404
    finally:
        _clear_overrides()
