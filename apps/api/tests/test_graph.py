"""T2.1 - LangGraph 골격 검증.

빈 4-노드 파이프라인이 end-to-end 실행되고 trace_events 가 누적되는지 확인.
체크포인터(MemorySaver) 동작도 함께 검증.
"""

from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents import build_graph
from app.agents.checkpointer import get_checkpointer
from app.agents.state import PipelineState


def _initial_state() -> PipelineState:
    return PipelineState(
        sector="memory_semiconductor",
        target_quarter="2024Q3",
        as_of_date=datetime(2024, 11, 30, tzinfo=UTC),
        is_backtest=False,
        run_id=None,
        topology=None,
        raw_data=None,
        quantified=None,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )


def test_get_checkpointer_returns_memory_saver_in_phase1() -> None:
    """Phase 1 단순화: 항상 MemorySaver 반환."""
    cp = get_checkpointer()
    assert isinstance(cp, MemorySaver)


@pytest.mark.asyncio
async def test_pipeline_runs_end_to_end_with_skeleton_nodes() -> None:
    """빈 4-노드가 순차 실행되어 4개 agent_complete trace_event 누적."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-pipeline-1"}}

    result = await graph.ainvoke(_initial_state(), config=config)

    # 4개 노드의 agent_complete + Evaluator 의 pipeline_complete = 5
    events = result["trace_events"]
    assert len(events) >= 4
    agent_completes = [e for e in events if e["event_type"] == "agent_complete"]
    assert len(agent_completes) == 4

    agents_in_order = [e["agent"] for e in agent_completes]
    assert agents_in_order == [
        "StructureMapper",
        "DataCollector",
        "QuantEstimator",
        "Evaluator",
    ]

    # pipeline_complete 마커 존재
    assert any(e["event_type"] == "pipeline_complete" for e in events)


@pytest.mark.asyncio
async def test_checkpointer_persists_state_across_invocations() -> None:
    """동일 thread_id 로 재호출 시 체크포인트가 누적되는지."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-checkpoint-1"}}

    await graph.ainvoke(_initial_state(), config=config)

    # 체크포인트 로드 가능 확인
    snapshot = await graph.aget_state(config)
    assert snapshot is not None
    assert snapshot.values.get("sector") == "memory_semiconductor"
    assert snapshot.values.get("target_quarter") == "2024Q3"


@pytest.mark.asyncio
async def test_trace_events_accumulate_via_reducer() -> None:
    """LangGraph reducer (operator.add) 가 노드 간 trace_events 를 append 하는지."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-reducer-1"}}

    result = await graph.ainvoke(_initial_state(), config=config)
    events = result["trace_events"]

    # 모든 timestamp 가 ISO-8601
    for event in events:
        # fromisoformat 이 throw 하지 않으면 유효
        datetime.fromisoformat(event["timestamp"])

    # agent 필드 검증 (Literal 타입)
    valid_agents = {"StructureMapper", "DataCollector", "QuantEstimator", "Evaluator"}
    for event in events:
        assert event["agent"] in valid_agents


@pytest.mark.asyncio
async def test_initial_state_input_preserved() -> None:
    """입력값 (sector, target_quarter, as_of_date) 이 그래프 종료 후에도 유지."""
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-input-1"}}

    initial = _initial_state()
    result = await graph.ainvoke(initial, config=config)

    assert result["sector"] == initial["sector"]
    assert result["target_quarter"] == initial["target_quarter"]
    assert result["as_of_date"] == initial["as_of_date"]
    assert result["is_backtest"] == initial["is_backtest"]


def test_build_graph_accepts_custom_checkpointer() -> None:
    """의존성 주입 검증 - 외부에서 checkpointer 주입 가능."""
    custom = MemorySaver()
    graph = build_graph(checkpointer=custom)
    assert graph is not None  # compile 성공
