"""QuantEstimator 노드 - 엣지별 매출 추정 + 통화 환산.

T2.5 책임 범위 (Phase 1 단순화):
1. raw_data 의 회사별 facts (revenue/cogs) 를 USD 환산 (FX rate)
2. 토폴로지 엣지별로 매출 분배 (휴리스틱: PRODUCT_SHARE × 1/buyer_count)
3. is_imputed=True 마킹 (Phase 1 모든 엣지 매출은 추정치)
4. repo.upsert_edge_metric + link_metric_citation
5. state["quantified"] 채움

V2+:
- 실 P × Q 계산 (관세청 / 공급사 IR / 가이던스 데이터 추가 시)
- 시장점유율 기반 정밀 분배
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from app.agents.deps import deps_from_config
from app.agents.nodes._trace import emit
from app.agents.state import PipelineState
from app.services.imputation import (
    get_product_share,
    impute_edge_revenue,
    to_usd,
)


def _index_facts_by_metric(
    facts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """ticker_facts -> {metric_name: fact_dict}."""
    return {f["metric_name"]: f for f in facts}


def _count_buyers_per_supplier_product(topology: dict[str, Any]) -> dict[tuple[str, str], int]:
    """(supplier_ticker, product) -> 같은 제품의 바이어 수."""
    counts: dict[tuple[str, str], int] = {}
    for edge in topology["edges"]:
        key = (edge["supplier_ticker"], edge["product_category"])
        counts[key] = counts.get(key, 0) + 1
    return counts


async def quantification_node(
    state: PipelineState, config: RunnableConfig
) -> dict[str, Any]:
    """엣지별 매출 추정 + USD 환산 + repo 영속화."""
    deps = deps_from_config(config)
    repo = deps.repo
    topology = state.get("topology")
    raw_data = state.get("raw_data")
    target_quarter = state.get("target_quarter", "")

    if not topology or not raw_data:
        return {
            "quantified": None,
            "trace_events": [
                emit(
                    "QuantEstimator",
                    "error",
                    {"reason": "missing_topology_or_raw_data"},
                ),
            ],
        }

    events: list[dict[str, Any]] = [
        emit("QuantEstimator", "agent_start", {"target_quarter": target_quarter})
    ]

    facts_by_ticker: dict[str, list[dict[str, Any]]] = raw_data.get(
        "facts_by_ticker", {}
    )
    edge_ids: dict[str, str] = raw_data.get("edge_ids", {})
    citation_ids_by_ticker: dict[str, list[str]] = raw_data.get(
        "citation_ids_by_ticker", {}
    )

    # 1. 회사별 USD 매출 산출 (FX 환산)
    supplier_revenue_usd: dict[str, float] = {}
    fx_warnings: list[str] = []
    for ticker, facts in facts_by_ticker.items():
        idx = _index_facts_by_metric(facts)
        rev = idx.get("revenue")
        if not rev:
            continue
        original_value = float(rev["value"])
        currency = rev["currency"]
        usd_value = to_usd(original_value, currency, deps.fx_rates, target_quarter)
        if currency != "USD" and usd_value == original_value:
            fx_warnings.append(f"{ticker}: missing FX for {currency}/USD@{target_quarter}")
        supplier_revenue_usd[ticker] = usd_value
    if fx_warnings:
        events.append(
            emit("QuantEstimator", "thought", {"fx_warnings": fx_warnings})
        )
    events.append(
        emit(
            "QuantEstimator",
            "thought",
            {
                "action": "fx_converted",
                "tickers_with_revenue": len(supplier_revenue_usd),
            },
        )
    )

    # 2. 토폴로지 엣지별 매출 분배 + repo 영속화
    buyers_per_supplier_product = _count_buyers_per_supplier_product(topology)
    edge_metrics: list[dict[str, Any]] = []
    persisted_count = 0

    for edge in topology["edges"]:
        supplier = edge["supplier_ticker"]
        buyer = edge["buyer_ticker"]
        product = edge["product_category"]
        edge_key = f"{supplier}->{buyer}|{product}"

        edge_id_str = edge_ids.get(edge_key)
        if not edge_id_str:
            continue
        edge_id = UUID(edge_id_str)

        supplier_rev = supplier_revenue_usd.get(supplier)
        if supplier_rev is None:
            # 공급사 매출 데이터 없음 → hypothesis only
            edge_metrics.append(
                {
                    "edge_id": edge_id_str,
                    "supplier_ticker": supplier,
                    "buyer_ticker": buyer,
                    "product_category": product,
                    "quarter": target_quarter,
                    "revenue_usd": None,
                    "is_imputed": True,
                    "is_hypothesis": True,
                    "confidence_score": 30,
                    "citation_ids": [],
                }
            )
            continue

        n_buyers = buyers_per_supplier_product.get((supplier, product), 1)
        edge_revenue_usd = impute_edge_revenue(
            supplier_total_revenue_usd=supplier_rev,
            product_category=product,
            n_buyers_for_product=n_buyers,
        )

        # 공급사 citation 들이 이 엣지 metric 의 근거
        supplier_citations = citation_ids_by_ticker.get(supplier, [])

        # repo 에 edge_metric 영속화
        metric_rec = repo.upsert_edge_metric(
            edge_id=edge_id,
            quarter=target_quarter,
            revenue=edge_revenue_usd,
            currency="USD",
            is_imputed=True,
            is_hypothesis=False,
            confidence_score=60,  # Phase 1 휴리스틱 기본 신뢰도
        )
        for cit_id in supplier_citations:
            try:
                repo.link_metric_citation(
                    metric_id=metric_rec.id,
                    citation_id=UUID(cit_id),
                    weight=1.0 / max(len(supplier_citations), 1),
                )
            except KeyError:
                # citation 이 repo 에 없는 경우 (방어적, 발생하면 안 됨)
                continue
        persisted_count += 1

        edge_metrics.append(
            {
                "edge_id": edge_id_str,
                "metric_id": str(metric_rec.id),
                "supplier_ticker": supplier,
                "buyer_ticker": buyer,
                "product_category": product,
                "quarter": target_quarter,
                "revenue_usd": edge_revenue_usd,
                "product_share": get_product_share(product),
                "n_buyers_for_product": n_buyers,
                "is_imputed": True,
                "is_hypothesis": False,
                "confidence_score": 60,
                "citation_ids": supplier_citations,
            }
        )

    # 3. confidence_map 누적 (Evaluator 가 사용)
    confidence_map: dict[str, Any] = {
        f"{m['supplier_ticker']}->{m['buyer_ticker']}|{m['product_category']}": m["confidence_score"]
        for m in edge_metrics
    }

    quantified = {
        "edge_metrics": edge_metrics,
        "supplier_revenue_usd": supplier_revenue_usd,
        "stats": {
            "edges_quantified": persisted_count,
            "edges_total": len(topology["edges"]),
            "fx_warnings": len(fx_warnings),
        },
    }

    events.append(
        emit(
            "QuantEstimator",
            "agent_complete",
            {
                "edges_quantified": persisted_count,
                "edges_total": len(topology["edges"]),
            },
        )
    )

    return {
        "quantified": quantified,
        "confidence_map": confidence_map,
        "trace_events": events,
    }
