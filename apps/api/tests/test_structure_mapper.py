"""T2.2 - StructureMapper 노드 + memory_semi 토폴로지 검증."""

from datetime import UTC, datetime

import pytest

from app.agents.nodes.structure_mapper import (
    _validate_topology_integrity,
    structure_mapping_node,
)
from app.agents.state import PipelineState
from app.agents.topology import (
    MEMORY_SEMICONDUCTOR_TOPOLOGY,
    get_topology,
)
from app.agents.topology.memory_semi import topology_summary

# ============================================================
# 토폴로지 정의 자체 검증
# ============================================================


def test_memory_topology_has_seven_nodes() -> None:
    """7개 기업 (DB seed 와 일치)."""
    assert len(MEMORY_SEMICONDUCTOR_TOPOLOGY["nodes"]) == 7
    tickers = {n["ticker"] for n in MEMORY_SEMICONDUCTOR_TOPOLOGY["nodes"]}
    expected = {"005930.KS", "000660.KS", "MU", "NVDA", "AMD", "INTC", "TSM"}
    assert tickers == expected


def test_memory_topology_has_at_least_ten_edges() -> None:
    """plan §T2.2 요구: 10여개 엣지."""
    assert len(MEMORY_SEMICONDUCTOR_TOPOLOGY["edges"]) >= 10


def test_memory_topology_matches_db_seed() -> None:
    """seed.sql 의 11개 엣지와 정확히 일치."""
    edges = MEMORY_SEMICONDUCTOR_TOPOLOGY["edges"]
    edge_set = {
        (e["supplier_ticker"], e["buyer_ticker"], e["product_category"]) for e in edges
    }
    # supabase/seed.sql 의 11개 엣지
    seed_edges = {
        ("000660.KS", "NVDA", "HBM"),
        ("005930.KS", "NVDA", "HBM"),
        ("MU", "NVDA", "HBM"),
        ("000660.KS", "AMD", "HBM"),
        ("005930.KS", "AMD", "HBM"),
        ("000660.KS", "INTC", "DRAM_DDR5"),
        ("005930.KS", "INTC", "DRAM_DDR5"),
        ("MU", "INTC", "DRAM_DDR5"),
        ("TSM", "NVDA", "FOUNDRY_COWOS"),
        ("TSM", "AMD", "FOUNDRY_COWOS"),
        ("TSM", "INTC", "FOUNDRY_5NM"),
    }
    assert edge_set == seed_edges


def test_topology_referential_integrity() -> None:
    """모든 edge 의 supplier/buyer 가 nodes 에 존재."""
    issues = _validate_topology_integrity(dict(MEMORY_SEMICONDUCTOR_TOPOLOGY))
    assert issues == []


def test_topology_no_self_loops() -> None:
    """A -> A 엣지 금지."""
    for edge in MEMORY_SEMICONDUCTOR_TOPOLOGY["edges"]:
        assert edge["supplier_ticker"] != edge["buyer_ticker"]


def test_lag_quarters_within_valid_range() -> None:
    """DB constraint: lag_quarters >= 0 and <= 8."""
    for edge in MEMORY_SEMICONDUCTOR_TOPOLOGY["edges"]:
        assert 0 <= edge["lag_quarters"] <= 8


def test_get_topology_known_sector() -> None:
    topo = get_topology("memory_semiconductor")
    assert topo["sector"] == "memory_semiconductor"


def test_get_topology_unknown_sector_raises() -> None:
    with pytest.raises(KeyError, match="Unsupported sector"):
        get_topology("oil_and_gas")


def test_topology_summary_shape() -> None:
    summary = topology_summary(dict(MEMORY_SEMICONDUCTOR_TOPOLOGY))
    assert summary["sector"] == "memory_semiconductor"
    assert summary["node_count"] == 7
    assert summary["edge_count"] == 11
    assert "HBM" in summary["products"]
    assert "DRAM_DDR5" in summary["products"]


# ============================================================
# 무결성 헬퍼 단위 테스트
# ============================================================


def test_validate_detects_unknown_supplier() -> None:
    bad = {
        "nodes": [{"ticker": "A"}, {"ticker": "B"}],
        "edges": [
            {
                "supplier_ticker": "GHOST",
                "buyer_ticker": "B",
                "product_category": "X",
                "lag_quarters": 0,
            }
        ],
    }
    issues = _validate_topology_integrity(bad)
    assert any("GHOST" in i and "supplier" in i for i in issues)


def test_validate_detects_self_loop() -> None:
    bad = {
        "nodes": [{"ticker": "A"}],
        "edges": [
            {
                "supplier_ticker": "A",
                "buyer_ticker": "A",
                "product_category": "X",
                "lag_quarters": 0,
            }
        ],
    }
    issues = _validate_topology_integrity(bad)
    assert any("self-loop" in i for i in issues)


# ============================================================
# 노드 통합
# ============================================================


def _state(sector: str) -> PipelineState:
    return PipelineState(
        sector=sector,
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


@pytest.mark.asyncio
async def test_structure_mapping_populates_topology() -> None:
    result = await structure_mapping_node(_state("memory_semiconductor"))

    assert result["topology"] is not None
    assert result["topology"]["sector"] == "memory_semiconductor"
    assert len(result["topology"]["nodes"]) == 7
    assert len(result["topology"]["edges"]) == 11

    events = result["trace_events"]
    assert events[0]["event_type"] == "agent_start"
    assert events[-1]["event_type"] == "agent_complete"
    assert events[-1]["payload"]["node_count"] == 7


@pytest.mark.asyncio
async def test_structure_mapping_empty_sector_emits_error() -> None:
    result = await structure_mapping_node(_state(""))
    assert result["topology"] is None
    assert result["trace_events"][0]["event_type"] == "error"


@pytest.mark.asyncio
async def test_structure_mapping_unknown_sector_raises_keyerror() -> None:
    """미지원 섹터는 KeyError 로 빠르게 실패."""
    with pytest.raises(KeyError, match="Unsupported sector"):
        await structure_mapping_node(_state("unknown_sector"))
