"""Quantification heuristics - 결측치 역산 + 통화 환산.

Phase 1 MVP 의 단순 휴리스틱:
- 회사별 분기 매출 (DART/EDGAR) 만 사용
- 엣지별 매출 = 공급사_매출 × PRODUCT_SHARE × (1 / 같은_제품_바이어_수)
- is_imputed = True (실 거래 데이터 없음, 간이 추정)

V2+ 에서:
- 실 P × Q (관세청, 공급사 IR, 가이던스)
- 시장점유율 데이터 (TrendForce 등)
- 산업 리포트 기반 정밀 분배
"""

from __future__ import annotations

from typing import Final

# 공급사 매출 중 해당 제품군이 차지하는 추정 비중 (Phase 1 휴리스틱)
# 출처: 공개 IR 자료 + 산업 분석 리포트 평균치 (2024년 기준)
PRODUCT_REVENUE_SHARE: Final[dict[str, float]] = {
    # HBM = AI 메모리 (SK Hynix 의 HBM 비중 ~25-35%, Samsung/Micron ~15-25%)
    "HBM": 0.30,
    # 서버 DDR5 (메모리 회사 매출의 ~20-25%)
    "DRAM_DDR5": 0.22,
    # CoWoS 패키징 (TSMC 매출의 ~12-18%)
    "FOUNDRY_COWOS": 0.15,
    # 5nm 첨단 공정 (TSMC 매출의 ~25%)
    "FOUNDRY_5NM": 0.25,
}

# 휴리스틱 미정의 제품의 fallback share (5%)
DEFAULT_PRODUCT_SHARE: Final[float] = 0.05


def get_product_share(product_category: str) -> float:
    """제품 카테고리의 공급사 매출 내 비중 반환."""
    return PRODUCT_REVENUE_SHARE.get(product_category, DEFAULT_PRODUCT_SHARE)


def to_usd(value: float, currency: str, fx_rates: dict[tuple[str, str], float], quarter: str) -> float:
    """KRW 등 비-USD 통화를 USD 로 환산.

    Args:
        value: 원래 통화 단위 값
        currency: ISO 통화 코드
        fx_rates: {(currency_pair, quarter): rate} - rate 는 1 USD = rate currency
        quarter: 환율 조회 분기

    Returns:
        USD 단위 값. 환율 미존재 시 원본 그대로 (warning 의 책임은 호출자).
    """
    if currency == "USD":
        return value
    pair = f"{currency}/USD"
    rate = fx_rates.get((pair, quarter))
    if not rate:
        # Phase 1: 환율 없으면 원본 반환 (호출자가 별도 로깅)
        return value
    # rate = 1 USD 가 N currency 단위 → value(currency) ÷ rate = USD
    return value / rate


def impute_edge_revenue(
    *,
    supplier_total_revenue_usd: float,
    product_category: str,
    n_buyers_for_product: int,
) -> float:
    """엣지 매출 추정 (Phase 1 휴리스틱).

    수식: supplier 매출 × 제품_비중 ÷ 동일제품_바이어_수
    """
    if n_buyers_for_product <= 0:
        return 0.0
    share = get_product_share(product_category)
    return supplier_total_revenue_usd * share / n_buyers_for_product
