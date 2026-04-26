"""LangGraph PipelineState - 7단계 파이프라인의 단일 진실 공유 상태.

설계 원칙 (architecture.md §4):
1. State는 직렬화 가능 (PostgresSaver 호환)
2. 노드는 partial dict를 return → LangGraph가 reducer로 합성
3. trace_events / reconciliation_errors 는 누적 (operator.add reducer)
4. as_of_date 는 시간 격리(Time Isolation)의 단일 진입점
"""

from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal, TypedDict


class TraceEvent(TypedDict):
    """SSE 스트림 송출용 단일 사고 이벤트.

    DB의 trace_events 테이블 (migration 8.) 과 1:1 매핑.
    """

    agent: Literal["StructureMapper", "DataCollector", "QuantEstimator", "Evaluator"]
    event_type: Literal[
        "agent_start",
        "thought",
        "tool_call",
        "tool_result",
        "graph_update",
        "agent_complete",
        "pipeline_complete",
        "error",
    ]
    payload: dict[str, Any]
    timestamp: str  # ISO-8601 UTC


def _merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """confidence_map 등 dict 누적용 reducer."""
    if not left:
        return right or {}
    if not right:
        return left
    return {**left, **right}


class PipelineState(TypedDict, total=False):
    """7단계 파이프라인의 공유 상태.

    `total=False` → 모든 필드 optional. 노드는 자기가 채우는 키만 return.
    """

    # ===== 입력 (사용자/runner가 invoke 시 제공) =====
    sector: str  # "memory_semiconductor"
    target_quarter: str  # "2024Q3"
    as_of_date: datetime  # 시간 격리 단일 진입점
    is_backtest: bool
    run_id: str | None  # runs 테이블 PK (DB 영속화 시)

    # ===== 노드 산출물 =====
    # StructureMapper -> 정적/동적 토폴로지
    topology: dict[str, Any] | None

    # DataCollector -> raw API 응답 + citations
    raw_data: dict[str, Any] | None

    # QuantEstimator -> 정량화된 edge_metrics (USD 환산 후)
    quantified: dict[str, Any] | None

    # Evaluator -> 정합성 오차 누적
    reconciliation_errors: Annotated[list[dict[str, Any]], add]

    # 노드별 confidence 점수 누적
    confidence_map: Annotated[dict[str, Any], _merge_dicts]

    # ===== Cross-cutting =====
    # 모든 노드가 trace_events 누적 → SSE로 실시간 스트림
    trace_events: Annotated[list[TraceEvent], add]
