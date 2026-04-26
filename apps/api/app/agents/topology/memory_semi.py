"""메모리 반도체 섹터 정적 토폴로지 (Phase 1).

설계 원칙:
- DB seed (supabase/seed.sql) 와 1:1 일치 → DataCollector 가 DB 매핑 시 무결성 보장
- 노드: ticker (DART/EDGAR 키 매칭에 사용), name, country, sector
- 엣지: supplier/buyer ticker, product_category, lag_quarters

향후 V2: DB로 이관 후 동적 로드. Phase 1 은 코드 내 하드코드로 단순화.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict


class TopologyNode(TypedDict):
    ticker: str
    name: str
    country: Literal["KR", "US", "JP", "TW", "CN", "NL"]
    sector: str


class TopologyEdge(TypedDict):
    supplier_ticker: str
    buyer_ticker: str
    product_category: str
    lag_quarters: int


class Topology(TypedDict):
    sector: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


# 메모리 반도체 supply chain (장비 + 메모리/Foundry + 팹리스/OEM)
# Phase 1: 7개 → 확장: 13개 기업, upstream(장비)~midstream(메모리/foundry)~downstream(OEM/팹리스) 전체 커버
MEMORY_SEMICONDUCTOR_TOPOLOGY: Final[Topology] = Topology(
    sector="memory_semiconductor",
    nodes=[
        # ---------- Midstream: 메모리 제조 ----------
        TopologyNode(
            ticker="005930.KS",
            name="Samsung Electronics",
            country="KR",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="000660.KS",
            name="SK Hynix",
            country="KR",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="MU",
            name="Micron Technology",
            country="US",
            sector="memory_semiconductor",
        ),
        # ---------- Midstream: Foundry ----------
        TopologyNode(
            ticker="TSM", name="TSMC", country="TW", sector="memory_semiconductor"
        ),
        # ---------- Downstream: 팹리스 / GPU / CPU ----------
        TopologyNode(
            ticker="NVDA",
            name="NVIDIA",
            country="US",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="AMD", name="AMD", country="US", sector="memory_semiconductor"
        ),
        TopologyNode(
            ticker="INTC", name="Intel", country="US", sector="memory_semiconductor"
        ),
        # ---------- Upstream: 반도체 장비 ----------
        TopologyNode(
            ticker="ASML",
            name="ASML Holding",
            country="NL",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="AMAT",
            name="Applied Materials",
            country="US",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="LRCX",
            name="Lam Research",
            country="US",
            sector="memory_semiconductor",
        ),
        # ---------- Downstream: 모바일 OEM / 팹리스 ----------
        TopologyNode(
            ticker="AAPL",
            name="Apple",
            country="US",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="QCOM",
            name="Qualcomm",
            country="US",
            sector="memory_semiconductor",
        ),
        TopologyNode(
            ticker="2454.TW",
            name="MediaTek",
            country="TW",
            sector="memory_semiconductor",
        ),
    ],
    edges=[
        # ============================================================
        # HBM: 메모리 3사 -> NVIDIA (AI GPU 필수)
        # ============================================================
        TopologyEdge(
            supplier_ticker="000660.KS",
            buyer_ticker="NVDA",
            product_category="HBM",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="005930.KS",
            buyer_ticker="NVDA",
            product_category="HBM",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="MU",
            buyer_ticker="NVDA",
            product_category="HBM",
            lag_quarters=1,
        ),
        # HBM: 메모리 2사 -> AMD MI300
        TopologyEdge(
            supplier_ticker="000660.KS",
            buyer_ticker="AMD",
            product_category="HBM",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="005930.KS",
            buyer_ticker="AMD",
            product_category="HBM",
            lag_quarters=1,
        ),
        # ============================================================
        # DRAM_DDR5: 메모리 3사 -> Intel (서버용)
        # ============================================================
        TopologyEdge(
            supplier_ticker="000660.KS",
            buyer_ticker="INTC",
            product_category="DRAM_DDR5",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="005930.KS",
            buyer_ticker="INTC",
            product_category="DRAM_DDR5",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="MU",
            buyer_ticker="INTC",
            product_category="DRAM_DDR5",
            lag_quarters=1,
        ),
        # ============================================================
        # FOUNDRY: TSMC -> 기존 팹리스 (CoWoS / 5nm)
        # ============================================================
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="NVDA",
            product_category="FOUNDRY_COWOS",
            lag_quarters=2,
        ),
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="AMD",
            product_category="FOUNDRY_COWOS",
            lag_quarters=2,
        ),
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="INTC",
            product_category="FOUNDRY_5NM",
            lag_quarters=2,
        ),
        # ============================================================
        # 신규 - Upstream 장비 -> 메모리/Foundry
        # 장비 lead time 길어서 lag_quarters 3-4
        # ============================================================
        # ASML EUV 노광 장비 (Samsung HBM 라인 / SK Hynix M16 / TSMC N3 EUV)
        TopologyEdge(
            supplier_ticker="ASML",
            buyer_ticker="005930.KS",
            product_category="EUV_LITHOGRAPHY",
            lag_quarters=4,
        ),
        TopologyEdge(
            supplier_ticker="ASML",
            buyer_ticker="000660.KS",
            product_category="EUV_LITHOGRAPHY",
            lag_quarters=4,
        ),
        TopologyEdge(
            supplier_ticker="ASML",
            buyer_ticker="TSM",
            product_category="EUV_LITHOGRAPHY",
            lag_quarters=4,
        ),
        # Applied Materials - 증착/식각/CMP 등 종합 장비
        TopologyEdge(
            supplier_ticker="AMAT",
            buyer_ticker="005930.KS",
            product_category="SEMI_EQUIPMENT",
            lag_quarters=3,
        ),
        TopologyEdge(
            supplier_ticker="AMAT",
            buyer_ticker="MU",
            product_category="SEMI_EQUIPMENT",
            lag_quarters=3,
        ),
        # Lam Research - 메모리 식각/CVD 특화
        TopologyEdge(
            supplier_ticker="LRCX",
            buyer_ticker="000660.KS",
            product_category="MEMORY_ETCH",
            lag_quarters=3,
        ),
        TopologyEdge(
            supplier_ticker="LRCX",
            buyer_ticker="MU",
            product_category="MEMORY_ETCH",
            lag_quarters=3,
        ),
        # ============================================================
        # 신규 - TSMC -> 팹리스 (모바일 SoC)
        # ============================================================
        # Apple A/M 시리즈 (TSMC N3/N4)
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="AAPL",
            product_category="FOUNDRY_3NM",
            lag_quarters=2,
        ),
        # Qualcomm Snapdragon (TSMC N4)
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="QCOM",
            product_category="FOUNDRY_4NM",
            lag_quarters=2,
        ),
        # MediaTek Dimensity (TSMC N4)
        TopologyEdge(
            supplier_ticker="TSM",
            buyer_ticker="2454.TW",
            product_category="FOUNDRY_4NM",
            lag_quarters=2,
        ),
        # ============================================================
        # 신규 - 메모리 3사 -> Apple (모바일 LPDDR / NAND)
        # ============================================================
        TopologyEdge(
            supplier_ticker="005930.KS",
            buyer_ticker="AAPL",
            product_category="MOBILE_DRAM",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="000660.KS",
            buyer_ticker="AAPL",
            product_category="MOBILE_DRAM",
            lag_quarters=1,
        ),
        TopologyEdge(
            supplier_ticker="MU",
            buyer_ticker="AAPL",
            product_category="MOBILE_DRAM",
            lag_quarters=1,
        ),
    ],
)


# 섹터 -> 토폴로지 매핑 (V2에서 다중 섹터 지원 시 확장)
_SECTOR_TOPOLOGIES: Final[dict[str, Topology]] = {
    "memory_semiconductor": MEMORY_SEMICONDUCTOR_TOPOLOGY,
}


def get_topology(sector: str) -> Topology:
    """섹터명으로 토폴로지 조회.

    Raises:
        KeyError: 미지원 섹터 (Phase 1 은 memory_semiconductor 만)
    """
    if sector not in _SECTOR_TOPOLOGIES:
        raise KeyError(
            f"Unsupported sector: {sector!r}. "
            f"Available: {sorted(_SECTOR_TOPOLOGIES.keys())}"
        )
    return _SECTOR_TOPOLOGIES[sector]


def topology_summary(topology: Topology) -> dict[str, Any]:
    """trace_event payload 용 요약."""
    return {
        "sector": topology["sector"],
        "node_count": len(topology["nodes"]),
        "edge_count": len(topology["edges"]),
        "products": sorted({e["product_category"] for e in topology["edges"]}),
    }
