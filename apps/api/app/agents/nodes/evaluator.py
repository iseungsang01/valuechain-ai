"""Evaluator 노드 - 정합성 검증 (Phase 1).

T2.6 책임 범위:
1. 각 바이어 별로 sum(inflow_usd) vs cogs_usd 정합성 검증 (10%p 임계)
2. reconciliation_errors 누적 + trace_events 송출
3. confidence_map 보강 (검증 실패 시 신뢰도 하향)

V1+:
- 시차(lag_quarters) 보정 - shift_quarter 헬퍼는 services/reconciliation.py 에 이미 구현
- Forward Conflict 감지 (가이던스 vs 가이던스)
- 신뢰도 점수 계산 정밀화
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.deps import deps_from_config
from app.agents.nodes._trace import emit
from app.agents.state import PipelineState
from app.services.reconciliation import (
    aggregate_inflows_by_buyer,
    compute_buyer_cogs_usd,
    detect_reconciliation_errors,
)


async def evaluation_node(
    state: PipelineState, config: RunnableConfig
) -> dict[str, Any]:
    """정합성 검증 + reconciliation_errors 누적."""
    deps = deps_from_config(config)
    quantified = state.get("quantified")
    raw_data = state.get("raw_data")
    target_quarter = state.get("target_quarter", "")

    if not quantified or not raw_data:
        return {
            "reconciliation_errors": [],
            "trace_events": [
                emit("Evaluator", "error", {"reason": "missing_quantified_or_raw_data"}),
                emit("Evaluator", "pipeline_complete", {}),
            ],
        }

    events: list[dict[str, Any]] = [
        emit("Evaluator", "agent_start", {"phase": "reconciliation"})
    ]

    buyer_cogs_usd = compute_buyer_cogs_usd(raw_data, deps.fx_rates, target_quarter)
    inflows_by_buyer = aggregate_inflows_by_buyer(quantified)

    events.append(
        emit(
            "Evaluator",
            "thought",
            {
                "buyer_cogs_count": len(buyer_cogs_usd),
                "buyer_inflow_count": len(inflows_by_buyer),
            },
        )
    )

    errors = detect_reconciliation_errors(
        buyer_cogs_usd=buyer_cogs_usd,
        inflows_by_buyer=inflows_by_buyer,
    )

    if errors:
        events.append(
            emit(
                "Evaluator",
                "thought",
                {
                    "errors_found": len(errors),
                    "high_severity": sum(1 for e in errors if e.get("severity") == "high"),
                },
            )
        )

    events.append(
        emit(
            "Evaluator",
            "agent_complete",
            {
                "errors_count": len(errors),
                "buyers_validated": len(buyer_cogs_usd),
            },
        )
    )
    events.append(emit("Evaluator", "pipeline_complete", {"target_quarter": target_quarter}))

    # confidence_map 보강 - reconciliation 실패한 buyer 의 모든 incoming 엣지 신뢰도 ↓
    failed_buyers = {e["buyer_ticker"] for e in errors if e.get("severity") in ("medium", "high")}
    confidence_updates: dict[str, int] = {}
    for m in quantified.get("edge_metrics", []):
        if m["buyer_ticker"] in failed_buyers:
            edge_key = f"{m['supplier_ticker']}->{m['buyer_ticker']}|{m['product_category']}"
            # Phase 1: 정합성 위반 시 30 으로 낮춤
            confidence_updates[edge_key] = 30

    return {
        "reconciliation_errors": errors,
        "confidence_map": confidence_updates,
        "trace_events": events,
    }
