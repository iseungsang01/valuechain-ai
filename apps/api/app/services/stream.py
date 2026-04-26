"""SSE 스트림 서비스 - LangGraph 파이프라인 → StreamEvent wire format.

T3.1: GET /api/runs/{run_id}/stream 의 백엔드 로직.

설계:
- graph.astream(stream_mode="updates") 로 노드별 partial state 수신
- 각 node update 의 trace_events 를 추출 → 1개씩 SSE event 로 송출
- topology / quantified / reconciliation_errors 가 채워질 때마다
  graph_update 이벤트 추가 송출 (UI 가 실시간으로 그래프 빌드 가능)
- 파이프라인 종료 후 'done' SSE 이벤트 (sse-starlette 표준)

이벤트 페이로드 형식: packages/shared/src/agents.ts StreamEventBase 와 일치.
- event_id (UUID v4) - 클라 dedup 용
- run_id, agent, type, timestamp, payload

오류 처리:
- 파이프라인 예외 → ErrorEvent 송출 후 RunStore 상태 'failed' 갱신
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from app.agents import build_graph
from app.agents.deps import PipelineDeps
from app.agents.state import PipelineState, TraceEvent
from app.middleware.error_handler import classify_exception
from app.services.runs import RunRecord, RunStore

logger = logging.getLogger(__name__)


# ============================================================
# Wire format helpers
# ============================================================


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _wire_event(
    *,
    run_id: str,
    agent: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """StreamEvent wire dict 생성. shared/src/agents.ts StreamEventBase 와 일치."""
    return {
        "event_id": str(uuid4()),
        "run_id": run_id,
        "agent": agent,
        "type": event_type,
        "timestamp": timestamp or _now_iso(),
        "payload": payload or {},
    }


def _trace_to_wire(run_id: str, trace: TraceEvent) -> dict[str, Any]:
    """백엔드 TraceEvent → 프론트 StreamEvent wire format 변환.

    - event_id (uuid4) 부여
    - run_id 결합
    - thought 이벤트는 payload 를 'text' 필드에도 mirror (UI 표시 편의)
    """
    payload = trace.get("payload") or {}
    event_type = trace["event_type"]

    wire: dict[str, Any] = {
        "event_id": str(uuid4()),
        "run_id": run_id,
        "agent": trace["agent"],
        "type": event_type,
        "timestamp": trace["timestamp"],
        "payload": payload,
    }

    # ThoughtEvent variant - text 필드 derive (shared/src/agents.ts ThoughtEvent.text)
    if event_type == "thought":
        wire["text"] = _derive_thought_text(payload)

    return wire


def _derive_thought_text(payload: dict[str, Any]) -> str:
    """thought payload → 사용자에게 보여줄 텍스트.

    payload 가 {"action": "..."} 형태면 action 값 사용,
    아니면 key=value 짧은 요약 생성.
    """
    if not payload:
        return ""
    if "action" in payload and isinstance(payload["action"], str):
        return payload["action"]
    if "summary" in payload and isinstance(payload["summary"], str):
        return payload["summary"]
    # 폴백 - key=value 요약 (최대 3개 key)
    items = list(payload.items())[:3]
    return ", ".join(f"{k}={v}" for k, v in items)


def _format_sse(data: dict[str, Any]) -> dict[str, str]:
    """sse-starlette EventSourceResponse 가 받는 dict 형식.

    {'event': type, 'data': json-string} → SSE 청크 'event: ...\\ndata: ...\\n\\n'.
    `id` 필드 추가로 클라 reconnect 시 Last-Event-ID 헤더 활용 가능.
    """
    return {
        "id": str(data.get("event_id", uuid4())),
        "event": str(data.get("type", "message")),
        "data": json.dumps(data, default=str, ensure_ascii=False),
    }


# ============================================================
# Graph update event 빌더
# ============================================================


def _build_graph_update(
    run_id: str,
    agent: str,
    *,
    topology: dict[str, Any] | None = None,
    quantified: dict[str, Any] | None = None,
    reconciliation_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """노드 산출물에서 graph_update SSE event 페이로드 생성.

    UI 의 React Flow 가 progressive 하게 그래프를 빌드하도록 partial_graph 제공.
    """
    partial_graph: dict[str, Any] = {}
    if topology is not None:
        partial_graph["nodes"] = topology.get("nodes", [])
        partial_graph["edges"] = topology.get("edges", [])
    if quantified is not None:
        partial_graph["edge_metrics"] = quantified.get("edge_metrics", [])
    if reconciliation_errors:
        partial_graph["reconciliation_errors"] = reconciliation_errors

    return _wire_event(
        run_id=run_id,
        agent=agent,
        event_type="graph_update",
        payload={"partial_graph": partial_graph},
    )


# ============================================================
# 메인 SSE 제너레이터
# ============================================================


def _initial_pipeline_state(run: RunRecord) -> PipelineState:
    """RunRecord → 초기 PipelineState. 노드들이 순차로 채워나감."""
    return PipelineState(
        sector=run.sector,
        target_quarter=run.target_quarter,
        as_of_date=run.as_of_date,
        is_backtest=run.is_backtest,
        run_id=run.run_id,
        topology=None,
        raw_data=None,
        quantified=None,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )


async def stream_pipeline_events(
    *,
    run: RunRecord,
    deps: PipelineDeps,
    store: RunStore,
) -> AsyncIterator[dict[str, str]]:
    """LangGraph 파이프라인을 실행하며 SSE 청크를 yield.

    호출자(routes/runs.py) 가 EventSourceResponse 로 wrap 하여 클라이언트에 전송.

    Args:
        run: 실행할 run 메타데이터
        deps: PipelineDeps (demo or real adapters)
        store: RunStore - 상태 갱신용

    Yields:
        sse-starlette 호환 dict {'id', 'event', 'data'}
    """
    run_id = run.run_id
    store.update_status(run_id, "running")

    # 1) 초기 lifecycle 이벤트 - 클라이언트가 SSE 연결 즉시 받음
    yield _format_sse(
        _wire_event(
            run_id=run_id,
            agent="StructureMapper",  # 첫 노드 기준 - lifecycle 이지만 agent literal 강제
            event_type="agent_start",
            payload={
                "kind": "pipeline_start",
                "sector": run.sector,
                "target_quarter": run.target_quarter,
            },
        )
    )

    graph = build_graph()
    initial_state = _initial_pipeline_state(run)
    config: dict[str, Any] = {
        "configurable": {"thread_id": run_id, "deps": deps},
    }

    # 누적 상태 추적 (graph_update 트리거용)
    last_topology: dict[str, Any] | None = None
    last_quantified: dict[str, Any] | None = None
    last_recon_errors: list[dict[str, Any]] = []

    try:
        async for chunk in graph.astream(
            cast(Any, initial_state), config=cast(Any, config), stream_mode="updates"
        ):
            # chunk = {"node_name": {<state_update>}}
            chunk_dict = cast(dict[str, dict[str, Any]], chunk)
            for node_name, update in chunk_dict.items():
                if not isinstance(update, dict):
                    continue

                # 1. trace_events 송출
                new_events: list[TraceEvent] = update.get("trace_events", []) or []
                for trace in new_events:
                    yield _format_sse(_trace_to_wire(run_id, trace))

                # 2. graph_update 자동 송출 (state 변화 감지)
                topology = update.get("topology")
                if topology and topology != last_topology:
                    last_topology = topology
                    yield _format_sse(
                        _build_graph_update(
                            run_id, "StructureMapper", topology=topology
                        )
                    )

                quantified = update.get("quantified")
                if quantified and quantified != last_quantified:
                    last_quantified = quantified
                    yield _format_sse(
                        _build_graph_update(
                            run_id, "QuantEstimator", quantified=quantified
                        )
                    )

                recon_errors = update.get("reconciliation_errors")
                if recon_errors and recon_errors != last_recon_errors:
                    last_recon_errors = recon_errors
                    yield _format_sse(
                        _build_graph_update(
                            run_id,
                            "Evaluator",
                            reconciliation_errors=recon_errors,
                        )
                    )

                _ = node_name  # 디버그용 - 추후 로깅에 활용 가능

        # 정상 종료
        store.update_status(run_id, "completed")

    except Exception as exc:
        # T4.2: 분류된 에러 → SSE error 페이로드 + RunStore 갱신.
        # classify_exception 이 도메인 예외(DART/EDGAR/Grounding/TimeIsolation)를
        # 사용자 친화 메시지로 변환. 운영 로그에는 details 가 별도 기록됨.
        classification = classify_exception(exc)
        logger.exception(
            "pipeline.failed",
            extra={
                "run_id": run_id,
                "category": classification.category.value,
                "error_code": classification.error_code,
                "details": classification.details,
            },
        )
        store.update_status(
            run_id, "failed", error_message=classification.user_message
        )
        yield _format_sse(
            _wire_event(
                run_id=run_id,
                # 에러가 어느 노드에서 발생했는지 추적 어려움 - 마지막 진행 단계 추론
                # 단순화: Evaluator 가 마지막이므로 그대로 사용. V2: state 의 last_agent 추적
                agent="Evaluator",
                event_type="error",
                payload=classification.to_payload(),
            )
        )
