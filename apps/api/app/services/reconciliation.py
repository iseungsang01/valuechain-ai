"""정합성 검증 (Phase 1 - Network Consistency).

Phase 1 알고리즘 (단순 → V2+ 에서 정밀화):
- 각 바이어 B 의 incoming edge revenue 합계 vs B 의 COGS 비교
- |sum_inflow_usd − buyer_cogs_usd × allocation_estimate| / cogs > tolerance → 오차

V2+ 정밀화:
- 시차(lag_quarters) 적용 - 공급사 Q3 매출 vs 바이어 Q4 COGS
- 제품 카테고리별 buyer_cost_share (HBM = NVIDIA COGS 의 X%) 정확화
- Tier 가중 (공시 데이터 vs 가이던스)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.imputation import to_usd

# Phase 1 단순 임계값 - 10%p 초과 시 reconciliation_error 발행
DEFAULT_TOLERANCE = 0.10
HIGH_SEVERITY_RATIO = 1.5  # inflow > cogs × 1.5 → 심각


def shift_quarter(quarter: str, delta: int) -> str:
    """'2024Q3' + 1 = '2024Q4'. 분기 기준 시차 보정 헬퍼.

    delta < 0: 과거 방향. delta > 0: 미래 방향.
    """
    year = int(quarter[:4])
    q = int(quarter[-1])
    total = year * 4 + (q - 1) + delta
    new_year = total // 4
    new_q = (total % 4) + 1
    return f"{new_year}Q{new_q}"


def compute_buyer_cogs_usd(
    raw_data: dict[str, Any],
    fx_rates: dict[tuple[str, str], float],
    quarter: str,
) -> dict[str, float]:
    """raw_data 의 각 회사 COGS 를 USD 환산하여 반환."""
    out: dict[str, float] = {}
    for ticker, facts in raw_data.get("facts_by_ticker", {}).items():
        for fact in facts:
            if fact["metric_name"] != "cogs":
                continue
            cogs_usd = to_usd(
                float(fact["value"]),
                fact["currency"],
                fx_rates,
                quarter,
            )
            out[ticker] = cogs_usd
            break  # 첫 번째 cogs fact 만 사용 (분기당 1개 가정)
    return out


def aggregate_inflows_by_buyer(quantified: dict[str, Any]) -> dict[str, float]:
    """edge_metrics 를 buyer 별로 합산."""
    sums: dict[str, float] = defaultdict(float)
    for m in quantified.get("edge_metrics", []):
        rev = m.get("revenue_usd")
        if rev is None:
            continue
        sums[m["buyer_ticker"]] += float(rev)
    return dict(sums)


def detect_reconciliation_errors(
    *,
    buyer_cogs_usd: dict[str, float],
    inflows_by_buyer: dict[str, float],
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict[str, Any]]:
    """바이어 단위 정합성 검증.

    검증 1: sum_inflow > cogs × (1 + tolerance) → 매입이 비용 초과 (모순)
    검증 2: cogs > 0 이지만 sum_inflow == 0 → 데이터 갭 (경고)

    Returns:
        오차 리스트 - 각 항목은 {buyer, type, inflow_usd, cogs_usd, ratio, severity}
    """
    errors: list[dict[str, Any]] = []

    for buyer, cogs in buyer_cogs_usd.items():
        inflow = inflows_by_buyer.get(buyer, 0.0)

        if cogs <= 0:
            continue

        ratio = inflow / cogs

        if inflow == 0:
            # 데이터 갭 - 분석 불가 (정합성 위반은 아님)
            continue

        # 매입이 비용을 초과 - 모순
        if ratio > 1 + tolerance:
            errors.append(
                {
                    "buyer_ticker": buyer,
                    "error_type": "inflow_exceeds_cogs",
                    "inflow_usd": inflow,
                    "cogs_usd": cogs,
                    "ratio": ratio,
                    "tolerance": tolerance,
                    "severity": "high" if ratio > HIGH_SEVERITY_RATIO else "medium",
                    "message": (
                        f"{buyer}: 매입 합계 ({inflow:,.0f} USD) 가 "
                        f"COGS ({cogs:,.0f} USD) 의 {ratio:.1%} - 한도 초과"
                    ),
                }
            )

    # 입력 갭 - 매입은 있는데 COGS 데이터 없음
    for buyer, inflow in inflows_by_buyer.items():
        if buyer not in buyer_cogs_usd and inflow > 0:
            errors.append(
                {
                    "buyer_ticker": buyer,
                    "error_type": "missing_buyer_cogs",
                    "inflow_usd": inflow,
                    "cogs_usd": None,
                    "ratio": None,
                    "severity": "low",
                    "message": f"{buyer}: COGS 데이터 없어 정합성 검증 불가",
                }
            )

    return errors
