"""SSE GET /api/runs/{id}/stream 엔드포인트 검증 (T3.1).

검증 범위:
1. SSE 응답 Content-Type / Cache-Control 헤더
2. 이벤트 wire format - StreamEventBase 필드 (event_id, run_id, agent, type, timestamp, payload)
3. 이벤트 순서 - 4개 agent_complete 가 StructureMapper → DataCollector → QuantEstimator → Evaluator
4. pipeline_complete 마커 존재
5. graph_update 이벤트가 topology / quantified / reconciliation_errors 변화 시 송출
6. 파이프라인 종료 후 RunStore 상태 'completed'
7. 데모 fixture 만으로 e2e 작동 (API 키 불필요)

도구: FastAPI TestClient (스트리밍 응답을 .iter_lines() 로 파싱).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.services.runs import InMemoryRunStore, get_run_store
from main import app


# ============================================================
# 헬퍼 - SSE chunk 파서
# ============================================================


def _parse_sse_stream(raw_lines: Iterator[str]) -> list[dict[str, Any]]:
    """raw SSE 응답 라인을 {event, data, id} 딕셔너리 리스트로 파싱.

    SSE 포맷: 'event: <type>\\nid: <id>\\ndata: <json>\\n\\n'
    빈 라인은 이벤트 구분자.
    """
    events: list[dict[str, Any]] = []
    current: dict[str, str] = {}
    for line in raw_lines:
        if not line.strip():
            if current:
                # data 가 JSON 이면 파싱, 아니면 raw 보관
                data_str = current.get("data", "")
                try:
                    parsed = json.loads(data_str)
                except json.JSONDecodeError:
                    parsed = {"raw": data_str}
                events.append(
                    {
                        "event": current.get("event"),
                        "id": current.get("id"),
                        "data": parsed,
                    }
                )
                current = {}
            continue
        if line.startswith(":"):
            # comment / heartbeat - 무시
            continue
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        # SSE 표준: 콜론 뒤 공백 한 칸은 무시
        if value.startswith(" "):
            value = value[1:]
        current[field.strip()] = value
    # 마지막 이벤트 flush
    if current:
        try:
            parsed = json.loads(current.get("data", ""))
        except json.JSONDecodeError:
            parsed = {"raw": current.get("data", "")}
        events.append(
            {"event": current.get("event"), "id": current.get("id"), "data": parsed}
        )
    return events


def _post_run_then_stream(client: TestClient) -> tuple[str, list[dict[str, Any]]]:
    """POST /api/runs → run_id 발급 → GET stream → 모든 이벤트 수집."""
    create_resp = client.post(
        "/api/runs",
        json={"sector": "memory_semiconductor", "target_quarter": "2024Q3"},
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["run_id"]

    with client.stream("GET", f"/api/runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        # sse-starlette 는 'text/event-stream; charset=...' 형태로 반환 가능
        content_type = resp.headers.get("content-type", "").lower()
        assert "text/event-stream" in content_type
        assert "no-cache" in resp.headers.get("cache-control", "").lower()

        events = _parse_sse_stream(resp.iter_lines())

    return run_id, events


# ============================================================
# 픽스처 - 격리된 RunStore
# ============================================================


@pytest.fixture
def isolated_store() -> Iterator[InMemoryRunStore]:
    store = InMemoryRunStore()
    app.dependency_overrides[get_run_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


# ============================================================
# 합격 기준 테스트
# ============================================================


def test_stream_returns_sse_content_type_and_headers(
    isolated_store: InMemoryRunStore,
) -> None:
    _ = isolated_store
    client = TestClient(app)
    create_resp = client.post(
        "/api/runs",
        json={"sector": "memory_semiconductor", "target_quarter": "2024Q3"},
    )
    run_id = create_resp.json()["run_id"]

    with client.stream("GET", f"/api/runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        ctype = resp.headers.get("content-type", "").lower()
        assert "text/event-stream" in ctype
        cache = resp.headers.get("cache-control", "").lower()
        assert "no-cache" in cache


def test_stream_emits_all_required_wire_fields(
    isolated_store: InMemoryRunStore,
) -> None:
    _ = isolated_store
    client = TestClient(app)
    run_id, events = _post_run_then_stream(client)

    assert len(events) > 0, "SSE stream produced zero events"
    for ev in events:
        data = ev["data"]
        assert isinstance(data, dict)
        # StreamEventBase 필수 필드
        assert "event_id" in data
        assert "run_id" in data
        assert data["run_id"] == run_id
        assert "agent" in data
        assert data["agent"] in {
            "StructureMapper",
            "DataCollector",
            "QuantEstimator",
            "Evaluator",
        }
        assert "type" in data
        assert "timestamp" in data
        assert "payload" in data


def test_stream_emits_four_agent_completes_in_order(
    isolated_store: InMemoryRunStore,
) -> None:
    _ = isolated_store
    client = TestClient(app)
    _, events = _post_run_then_stream(client)

    completes = [
        cast(dict[str, Any], e["data"])
        for e in events
        if cast(dict[str, Any], e["data"]).get("type") == "agent_complete"
    ]
    agents_in_order = [c["agent"] for c in completes]
    assert agents_in_order == [
        "StructureMapper",
        "DataCollector",
        "QuantEstimator",
        "Evaluator",
    ]


def test_stream_emits_pipeline_complete_marker(
    isolated_store: InMemoryRunStore,
) -> None:
    _ = isolated_store
    client = TestClient(app)
    _, events = _post_run_then_stream(client)

    types = [cast(dict[str, Any], e["data"]).get("type") for e in events]
    assert "pipeline_complete" in types


def test_stream_emits_graph_update_events_with_partial_graph(
    isolated_store: InMemoryRunStore,
) -> None:
    """Stream service 가 합성한 graph_update 는 partial_graph 페이로드 보유.

    노드가 자체 emit 한 graph_update (action descriptor) 와 구분 - 둘 다 valid 하지만
    프론트가 React Flow 갱신용으로 사용하는 건 partial_graph 가 있는 변종.
    """
    _ = isolated_store
    client = TestClient(app)
    _, events = _post_run_then_stream(client)

    # 모든 graph_update (node-emitted + stream-synthesized)
    graph_updates = [
        cast(dict[str, Any], e["data"])
        for e in events
        if cast(dict[str, Any], e["data"]).get("type") == "graph_update"
    ]
    assert len(graph_updates) >= 2  # 최소 node-emitted 2 + synthesized 2

    # partial_graph 페이로드를 가진 변종만 필터 (UI 갱신용)
    synthesized = [
        g for g in graph_updates if "partial_graph" in g.get("payload", {})
    ]
    assert len(synthesized) >= 2, "stream service 가 합성한 graph_update 부족"

    partial_graphs = [g["payload"]["partial_graph"] for g in synthesized]
    # StructureMapper 합성: nodes/edges
    assert any("nodes" in p and len(p["nodes"]) > 0 for p in partial_graphs)
    # QuantEstimator 합성: edge_metrics
    assert any(
        "edge_metrics" in p and len(p["edge_metrics"]) > 0 for p in partial_graphs
    )


def test_stream_marks_run_completed_in_store(
    isolated_store: InMemoryRunStore,
) -> None:
    client = TestClient(app)
    run_id, _ = _post_run_then_stream(client)
    record = isolated_store.get(run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.completed_at is not None


def test_stream_event_ids_are_unique(isolated_store: InMemoryRunStore) -> None:
    _ = isolated_store
    client = TestClient(app)
    _, events = _post_run_then_stream(client)
    event_ids = [
        cast(dict[str, Any], e["data"]).get("event_id")
        for e in events
        if isinstance(e["data"], dict)
    ]
    assert len(event_ids) == len(set(event_ids)), "event_id duplicates present"


def test_stream_payload_field_passes_through_raw_dict(
    isolated_store: InMemoryRunStore,
) -> None:
    """thought 이벤트는 payload 원본 + text(파생) 둘 다 포함해야 함."""
    _ = isolated_store
    client = TestClient(app)
    _, events = _post_run_then_stream(client)

    thoughts = [
        cast(dict[str, Any], e["data"])
        for e in events
        if cast(dict[str, Any], e["data"]).get("type") == "thought"
    ]
    assert len(thoughts) > 0
    for t in thoughts:
        assert "payload" in t and isinstance(t["payload"], dict)
        # text 는 항상 string (빈 문자열 가능)
        assert "text" in t and isinstance(t["text"], str)
