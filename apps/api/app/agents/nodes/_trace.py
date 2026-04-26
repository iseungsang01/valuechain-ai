"""공통 trace_event 헬퍼."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.agents.state import TraceEvent


def emit(
    agent: Literal["StructureMapper", "DataCollector", "QuantEstimator", "Evaluator"],
    event_type: Literal[
        "agent_start",
        "thought",
        "tool_call",
        "tool_result",
        "graph_update",
        "agent_complete",
        "pipeline_complete",
        "error",
    ],
    payload: dict[str, Any] | None = None,
) -> TraceEvent:
    """trace_event 단일 항목 생성. UTC ISO-8601 타임스탬프 자동 부착."""
    return TraceEvent(
        agent=agent,
        event_type=event_type,
        payload=payload or {},
        timestamp=datetime.now(UTC).isoformat(),
    )
