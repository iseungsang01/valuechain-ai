"""LangGraph StateGraph 정의 - 4 노드 선형 파이프라인 (Phase 1).

설계 (architecture.md §4):
    StructureMapper -> DataCollector -> QuantEstimator -> Evaluator -> END

V2+ 에서 reconciliation 실패 시 quantification 으로 되돌아가는 conditional edge 추가 예정.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from app.agents.checkpointer import get_checkpointer
from app.agents.nodes import (
    data_collection_node,
    evaluation_node,
    quantification_node,
    structure_mapping_node,
)
from app.agents.state import PipelineState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """4-노드 파이프라인 컴파일.

    Args:
        checkpointer: 미지정 시 MemorySaver (테스트/로컬). PostgresSaver 주입 가능.

    Returns:
        Compiled StateGraph - .ainvoke / .astream_events 호출 가능.
    """
    graph: StateGraph = StateGraph(PipelineState)

    graph.add_node("structure_mapping", structure_mapping_node)
    graph.add_node("data_collection", data_collection_node)
    graph.add_node("quantification", quantification_node)
    graph.add_node("evaluation", evaluation_node)

    graph.set_entry_point("structure_mapping")
    graph.add_edge("structure_mapping", "data_collection")
    graph.add_edge("data_collection", "quantification")
    graph.add_edge("quantification", "evaluation")
    graph.add_edge("evaluation", END)

    if checkpointer is None:
        checkpointer = get_checkpointer()

    return graph.compile(checkpointer=checkpointer)
