"""StructureMapper 노드 - 섹터별 정적 토폴로지 주입 (Phase 1).

T2.2: 메모리 반도체 토폴로지 하드코드 (V2+ 에서 동적 로드).

입력: state["sector"]
출력: state["topology"] = {sector, nodes, edges}
     무결성: 모든 edge.supplier/buyer 는 nodes 에 존재해야 함
"""

from __future__ import annotations

from typing import Any

from app.agents.nodes._trace import emit
from app.agents.state import PipelineState
from app.agents.topology import get_topology
from app.agents.topology.memory_semi import topology_summary


def _validate_topology_integrity(topology: dict[str, Any]) -> list[str]:
    """edge supplier/buyer 모두 nodes 에 존재하는지 검증."""
    tickers = {n["ticker"] for n in topology["nodes"]}
    issues: list[str] = []
    for idx, edge in enumerate(topology["edges"]):
        if edge["supplier_ticker"] not in tickers:
            issues.append(
                f"edge[{idx}] supplier {edge['supplier_ticker']!r} not in nodes"
            )
        if edge["buyer_ticker"] not in tickers:
            issues.append(
                f"edge[{idx}] buyer {edge['buyer_ticker']!r} not in nodes"
            )
        if edge["supplier_ticker"] == edge["buyer_ticker"]:
            issues.append(f"edge[{idx}] self-loop on {edge['supplier_ticker']!r}")
    return issues


async def structure_mapping_node(state: PipelineState) -> dict[str, Any]:
    """섹터 토폴로지를 PipelineState 에 채움.

    Raises:
        KeyError: 미지원 섹터 (get_topology 가 raise)
    """
    sector = state.get("sector", "")
    if not sector:
        return {
            "topology": None,
            "trace_events": [
                emit("StructureMapper", "error", {"reason": "sector is empty"}),
            ],
        }

    topology = dict(get_topology(sector))  # TypedDict -> dict (직렬화 호환)

    issues = _validate_topology_integrity(topology)
    if issues:
        return {
            "topology": None,
            "trace_events": [
                emit(
                    "StructureMapper",
                    "error",
                    {"reason": "integrity_violation", "issues": issues},
                ),
            ],
        }

    summary = topology_summary(topology)
    return {
        "topology": topology,
        "trace_events": [
            emit("StructureMapper", "agent_start", {"sector": sector}),
            emit("StructureMapper", "thought", {"action": "loading_topology"}),
            emit("StructureMapper", "agent_complete", summary),
        ],
    }
