"""T2.6 - Evaluator 노드 + reconciliation 서비스 검증."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.agents.deps import PipelineDeps
from app.agents.nodes.evaluator import evaluation_node
from app.agents.state import PipelineState
from app.agents.topology import MEMORY_SEMICONDUCTOR_TOPOLOGY
from app.db.repository import InMemoryRepository
from app.services.reconciliation import (
    DEFAULT_TOLERANCE,
    aggregate_inflows_by_buyer,
    compute_buyer_cogs_usd,
    detect_reconciliation_errors,
    shift_quarter,
)

# ============================================================
# 시차 (lag) 헬퍼 단위 테스트
# ============================================================


def test_shift_quarter_within_year() -> None:
    assert shift_quarter("2024Q1", 1) == "2024Q2"
    assert shift_quarter("2024Q3", 1) == "2024Q4"


def test_shift_quarter_across_year_boundary() -> None:
    assert shift_quarter("2024Q4", 1) == "2025Q1"
    assert shift_quarter("2024Q1", -1) == "2023Q4"


def test_shift_quarter_multi_quarter() -> None:
    assert shift_quarter("2024Q1", 4) == "2025Q1"
    assert shift_quarter("2024Q3", 5) == "2025Q4"
    assert shift_quarter("2024Q1", -8) == "2022Q1"


# ============================================================
# 헬퍼 단위 테스트
# ============================================================


def test_compute_buyer_cogs_converts_currency() -> None:
    raw_data = {
        "facts_by_ticker": {
            "000660.KS": [
                {
                    "metric_name": "cogs",
                    "value": 13_400_000_000_000.0,
                    "currency": "KRW",
                    "quarter": "2024Q3",
                    "citation_id": "x",
                }
            ],
            "MU": [
                {
                    "metric_name": "cogs",
                    "value": 5_000_000_000.0,
                    "currency": "USD",
                    "quarter": "2024Q3",
                    "citation_id": "y",
                }
            ],
        }
    }
    fx = {("KRW/USD", "2024Q3"): 1340.0}

    result = compute_buyer_cogs_usd(raw_data, fx, "2024Q3")
    assert result["000660.KS"] == pytest.approx(10_000_000_000.0)
    assert result["MU"] == 5_000_000_000.0


def test_compute_buyer_cogs_skips_non_cogs_facts() -> None:
    raw_data = {
        "facts_by_ticker": {
            "MU": [
                {
                    "metric_name": "revenue",
                    "value": 7e9,
                    "currency": "USD",
                    "quarter": "2024Q3",
                    "citation_id": "x",
                }
            ]
        }
    }
    result = compute_buyer_cogs_usd(raw_data, {}, "2024Q3")
    assert result == {}


def test_aggregate_inflows_sums_per_buyer() -> None:
    quantified = {
        "edge_metrics": [
            {"supplier_ticker": "MU", "buyer_ticker": "NVDA", "revenue_usd": 100.0, "product_category": "HBM"},
            {"supplier_ticker": "000660.KS", "buyer_ticker": "NVDA", "revenue_usd": 200.0, "product_category": "HBM"},
            {"supplier_ticker": "TSM", "buyer_ticker": "AMD", "revenue_usd": 50.0, "product_category": "FOUNDRY_COWOS"},
            {"supplier_ticker": "MU", "buyer_ticker": "NVDA", "revenue_usd": None, "product_category": "X"},
        ]
    }
    result = aggregate_inflows_by_buyer(quantified)
    assert result["NVDA"] == 300.0  # None 은 무시
    assert result["AMD"] == 50.0


def test_aggregate_inflows_handles_empty() -> None:
    assert aggregate_inflows_by_buyer({"edge_metrics": []}) == {}


# ============================================================
# detect_reconciliation_errors
# ============================================================


def test_detect_no_errors_when_inflow_within_tolerance() -> None:
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 1000.0},
        inflows_by_buyer={"NVDA": 1050.0},  # 5% over - 허용 범위
    )
    assert errors == []


def test_detect_error_when_inflow_exceeds_cogs() -> None:
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 1000.0},
        inflows_by_buyer={"NVDA": 1500.0},  # 50% over - 한도 초과
    )
    assert len(errors) == 1
    assert errors[0]["error_type"] == "inflow_exceeds_cogs"
    assert errors[0]["buyer_ticker"] == "NVDA"
    assert errors[0]["ratio"] == pytest.approx(1.5)


def test_detect_high_severity_at_50pct_over() -> None:
    """ratio > 1.5 = high severity."""
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 1000.0},
        inflows_by_buyer={"NVDA": 1600.0},
    )
    assert errors[0]["severity"] == "high"


def test_detect_medium_severity_at_25pct_over() -> None:
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 1000.0},
        inflows_by_buyer={"NVDA": 1250.0},
    )
    assert errors[0]["severity"] == "medium"


def test_detect_skips_zero_or_negative_cogs() -> None:
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 0.0},
        inflows_by_buyer={"NVDA": 1000.0},
    )
    assert errors == []


def test_detect_skips_zero_inflow_as_data_gap() -> None:
    """inflow == 0 은 데이터 갭 - 정합성 위반은 아님."""
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"NVDA": 1000.0},
        inflows_by_buyer={},
    )
    assert errors == []


def test_detect_flags_missing_cogs_when_inflow_present() -> None:
    """매입은 있는데 COGS 데이터 없음 = low severity 경고."""
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={},
        inflows_by_buyer={"AMD": 500.0},
    )
    assert len(errors) == 1
    assert errors[0]["error_type"] == "missing_buyer_cogs"
    assert errors[0]["severity"] == "low"


def test_detect_default_tolerance_is_10_percent() -> None:
    """tolerance 기본값 검증."""
    assert DEFAULT_TOLERANCE == 0.10
    # 정확히 +10% 는 통과
    assert (
        detect_reconciliation_errors(
            buyer_cogs_usd={"X": 100.0},
            inflows_by_buyer={"X": 110.0},
        )
        == []
    )
    # +11% 는 차단
    errors = detect_reconciliation_errors(
        buyer_cogs_usd={"X": 100.0},
        inflows_by_buyer={"X": 111.0},
    )
    assert len(errors) == 1


# ============================================================
# evaluation_node 통합
# ============================================================


def _state(quantified: dict[str, Any] | None, raw_data: dict[str, Any] | None) -> PipelineState:
    return PipelineState(
        sector="memory_semiconductor",
        target_quarter="2024Q3",
        as_of_date=datetime(2024, 11, 30, tzinfo=UTC),
        is_backtest=False,
        run_id=None,
        topology=dict(MEMORY_SEMICONDUCTOR_TOPOLOGY),
        raw_data=raw_data,
        quantified=quantified,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )


def _config(deps: PipelineDeps) -> dict[str, Any]:
    return {"configurable": {"deps": deps}}


@pytest.mark.asyncio
async def test_evaluator_no_errors_when_balanced() -> None:
    """정상 케이스: inflow ≈ cogs → 0 errors."""
    raw_data = {
        "facts_by_ticker": {
            "NVDA": [
                {"metric_name": "cogs", "value": 10e9, "currency": "USD", "quarter": "2024Q3", "citation_id": "x"}
            ]
        }
    }
    quantified = {
        "edge_metrics": [
            {"supplier_ticker": "MU", "buyer_ticker": "NVDA", "revenue_usd": 9e9, "product_category": "HBM"}
        ]
    }
    deps = PipelineDeps(repo=InMemoryRepository())
    result = await evaluation_node(_state(quantified, raw_data), _config(deps))

    assert result["reconciliation_errors"] == []
    # pipeline_complete 마커
    assert any(
        e["event_type"] == "pipeline_complete" for e in result["trace_events"]
    )


@pytest.mark.asyncio
async def test_evaluator_detects_injected_inflow_exceeds_cogs() -> None:
    """의도적 오차 주입: inflow >> cogs → error 1건 발견 (T2.6 QA 요구)."""
    raw_data = {
        "facts_by_ticker": {
            "NVDA": [
                {"metric_name": "cogs", "value": 5e9, "currency": "USD", "quarter": "2024Q3", "citation_id": "x"}
            ]
        }
    }
    quantified = {
        "edge_metrics": [
            {"supplier_ticker": "MU", "buyer_ticker": "NVDA", "revenue_usd": 8e9, "product_category": "HBM"},
            {"supplier_ticker": "000660.KS", "buyer_ticker": "NVDA", "revenue_usd": 4e9, "product_category": "HBM"},
        ]
    }
    # NVDA 매입 12B vs COGS 5B = 240% → high severity
    deps = PipelineDeps(repo=InMemoryRepository())
    result = await evaluation_node(_state(quantified, raw_data), _config(deps))

    errors = result["reconciliation_errors"]
    assert len(errors) == 1
    assert errors[0]["buyer_ticker"] == "NVDA"
    assert errors[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_evaluator_lowers_confidence_for_failed_buyer() -> None:
    """정합성 위반 buyer 의 모든 incoming 엣지 confidence ↓."""
    raw_data = {
        "facts_by_ticker": {
            "NVDA": [
                {"metric_name": "cogs", "value": 1e9, "currency": "USD", "quarter": "2024Q3", "citation_id": "x"}
            ]
        }
    }
    quantified = {
        "edge_metrics": [
            {"supplier_ticker": "MU", "buyer_ticker": "NVDA", "revenue_usd": 5e9, "product_category": "HBM"},
            {"supplier_ticker": "TSM", "buyer_ticker": "NVDA", "revenue_usd": 3e9, "product_category": "FOUNDRY_COWOS"},
        ]
    }
    deps = PipelineDeps(repo=InMemoryRepository())
    result = await evaluation_node(_state(quantified, raw_data), _config(deps))

    confidence = result["confidence_map"]
    assert confidence["MU->NVDA|HBM"] == 30
    assert confidence["TSM->NVDA|FOUNDRY_COWOS"] == 30


@pytest.mark.asyncio
async def test_evaluator_handles_missing_inputs() -> None:
    """raw_data / quantified 둘 중 하나라도 없으면 빈 결과."""
    deps = PipelineDeps(repo=InMemoryRepository())
    result = await evaluation_node(_state(None, None), _config(deps))

    assert result["reconciliation_errors"] == []
    error_events = [e for e in result["trace_events"] if e["event_type"] == "error"]
    assert error_events


@pytest.mark.asyncio
async def test_evaluator_emits_proper_trace_sequence() -> None:
    """agent_start → thought → agent_complete → pipeline_complete 순서."""
    raw_data = {"facts_by_ticker": {}}
    quantified = {"edge_metrics": []}
    deps = PipelineDeps(repo=InMemoryRepository())
    result = await evaluation_node(_state(quantified, raw_data), _config(deps))

    types = [e["event_type"] for e in result["trace_events"]]
    assert types[0] == "agent_start"
    assert "agent_complete" in types
    assert types[-1] == "pipeline_complete"
