"""Week 2 합격 기준 E2E 검증.

> "4개 LangGraph 노드가 빈 그래프부터 정합성 검증까지 end-to-end 작동"

mock 어댑터 + 실제 토폴로지 + InMemoryRepository 로 전체 파이프라인 실행.
"""

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.agents import build_graph
from app.agents.deps import PipelineDeps
from app.agents.state import PipelineState
from app.db.repository import InMemoryRepository
from app.sources.types import (
    DartFinancialFact,
    EdgarFinancialFact,
    SourceCitation,
)

# ============================================================
# 테스트 픽스처 - 실제와 비슷한 메모리 반도체 2024Q3 데이터
# ============================================================


def _dart_fact(
    corp_code: str,
    ticker: str,
    metric: str,
    value: float,
    rcept_no: str,
    publish: date = date(2024, 11, 14),
) -> DartFinancialFact:
    return DartFinancialFact(
        company_ticker=ticker,
        quarter="2024Q3",
        metric_name=metric,
        value=value,
        currency="KRW",
        corp_code=corp_code,
        reprt_code="11014",
        citation=SourceCitation(
            source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",  # type: ignore[arg-type]
            source_type="DART",
            source_tier=1,
            publish_date=publish,
            disclosure_id=rcept_no,
        ),
    )


def _edgar_fact(
    cik: str,
    ticker: str,
    metric: str,
    value: float,
    accn: str,
    publish: date = date(2024, 9, 30),
) -> EdgarFinancialFact:
    return EdgarFinancialFact(
        company_ticker=ticker,
        quarter="2024Q3",
        metric_name=metric,
        value=value,
        currency="USD",
        cik=cik,
        concept="us-gaap:Revenues" if metric == "revenue" else "us-gaap:CostOfRevenue",
        form_type="10-Q",
        citation=SourceCitation(
            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={cik}",  # type: ignore[arg-type]
            source_type="EDGAR",
            source_tier=1,
            publish_date=publish,
            disclosure_id=accn,
        ),
    )


# 2024Q3 실 데이터 근사값 (공시 수치 기반)
DART_FIXTURES = {
    "00164779": [  # SK Hynix
        _dart_fact("00164779", "000660.KS", "revenue", 17_573_000_000_000.0, "DART-SK-2024Q3"),
        _dart_fact("00164779", "000660.KS", "cogs", 9_840_000_000_000.0, "DART-SK-2024Q3"),
    ],
    "00126380": [  # Samsung Electronics
        _dart_fact("00126380", "005930.KS", "revenue", 79_088_000_000_000.0, "DART-SS-2024Q3"),
        _dart_fact("00126380", "005930.KS", "cogs", 56_220_000_000_000.0, "DART-SS-2024Q3"),
    ],
}

EDGAR_REVENUE_FIXTURES = {
    "0000723125": [_edgar_fact("0000723125", "MU", "revenue", 7_750_000_000.0, "MU-2024Q3")],
    "0001045810": [_edgar_fact("0001045810", "NVDA", "revenue", 30_040_000_000.0, "NVDA-2024Q3")],
    "0000002488": [_edgar_fact("0000002488", "AMD", "revenue", 6_820_000_000.0, "AMD-2024Q3")],
    "0000050863": [_edgar_fact("0000050863", "INTC", "revenue", 13_280_000_000.0, "INTC-2024Q3")],
    "0001046179": [_edgar_fact("0001046179", "TSM", "revenue", 23_500_000_000.0, "TSM-2024Q3")],
}

EDGAR_COGS_FIXTURES = {
    "0000723125": [_edgar_fact("0000723125", "MU", "cogs", 5_310_000_000.0, "MU-2024Q3")],
    "0001045810": [_edgar_fact("0001045810", "NVDA", "cogs", 7_660_000_000.0, "NVDA-2024Q3")],
    "0000002488": [_edgar_fact("0000002488", "AMD", "cogs", 3_870_000_000.0, "AMD-2024Q3")],
    "0000050863": [_edgar_fact("0000050863", "INTC", "cogs", 9_950_000_000.0, "INTC-2024Q3")],
    "0001046179": [_edgar_fact("0001046179", "TSM", "cogs", 9_500_000_000.0, "TSM-2024Q3")],
}


class _MockDart:
    """DartClient 인터페이스 충족 (kwargs 시그니처 매칭 필수)."""

    def __init__(self, fixtures: dict[str, list[DartFinancialFact]]) -> None:
        self.fixtures = fixtures

    async def get_quarterly_revenue_cogs(
        self,
        *,
        corp_code: str,
        year: int,  # noqa: ARG002 - 시그니처 매칭용
        reprt_code: str,  # noqa: ARG002
        ticker: str = "",  # noqa: ARG002
    ) -> list[DartFinancialFact]:
        return self.fixtures.get(corp_code, [])


class _MockEdgar:
    """EdgarClient 인터페이스 충족."""

    def __init__(
        self,
        rev: dict[str, list[EdgarFinancialFact]],
        cogs: dict[str, list[EdgarFinancialFact]],
    ) -> None:
        self.rev = rev
        self.cogs = cogs

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"_cik_marker": cik}

    def extract_quarterly(
        self,
        facts: dict[str, Any],
        concept: str,
        ticker: str,  # noqa: ARG002 - 시그니처 매칭용
    ) -> list[EdgarFinancialFact]:
        cik = facts.get("_cik_marker", "")
        if "Revenue" in concept:
            return self.rev.get(cik, [])
        return self.cogs.get(cik, [])


def _make_realistic_deps() -> PipelineDeps:
    @asynccontextmanager
    async def dart_factory():
        yield _MockDart(DART_FIXTURES)

    @asynccontextmanager
    async def edgar_factory():
        yield _MockEdgar(EDGAR_REVENUE_FIXTURES, EDGAR_COGS_FIXTURES)

    return PipelineDeps(
        repo=InMemoryRepository(),
        dart_factory=dart_factory,
        edgar_factory=edgar_factory,
        # 2024Q3 평균: 1USD ≈ 1340 KRW (실제 값 근사)
        fx_rates={("KRW/USD", "2024Q3"): 1340.0},
    )


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


# ============================================================
# Week 2 합격 기준
# ============================================================


@pytest.mark.asyncio
async def test_e2e_full_pipeline_runs_through_all_four_nodes() -> None:
    """4개 노드가 순차 실행되어 final state 가 모든 산출물 보유."""
    graph = build_graph()
    deps = _make_realistic_deps()
    config: dict[str, Any] = {
        "configurable": {"thread_id": "e2e-1", "deps": deps},
    }

    result = await graph.ainvoke(_initial_state(), config=config)

    # 1. StructureMapper → topology 채움
    assert result["topology"] is not None
    assert len(result["topology"]["nodes"]) == 13
    assert len(result["topology"]["edges"]) == 24

    # 2. DataCollector → raw_data + repo 영속화
    assert result["raw_data"] is not None
    facts = result["raw_data"]["facts_by_ticker"]
    assert "000660.KS" in facts  # SK Hynix DART
    assert "MU" in facts  # Micron EDGAR
    assert "NVDA" in facts

    # 3. QuantEstimator → quantified + edge_metrics
    assert result["quantified"] is not None
    edge_metrics = result["quantified"]["edge_metrics"]
    # 모든 24개 엣지가 entry 보유 (revenue 가 None 인 hypothesis 도 포함)
    assert len(edge_metrics) == 24

    # 적어도 SK Hynix → NVIDIA HBM 엣지는 revenue_usd 가 채워짐
    sk_to_nvda = next(
        m
        for m in edge_metrics
        if m["supplier_ticker"] == "000660.KS"
        and m["buyer_ticker"] == "NVDA"
        and m["product_category"] == "HBM"
    )
    assert sk_to_nvda["revenue_usd"] is not None
    assert sk_to_nvda["revenue_usd"] > 0
    assert sk_to_nvda["is_imputed"] is True

    # 4. Evaluator → reconciliation_errors (있을 수도, 없을 수도)
    assert "reconciliation_errors" in result
    # 실제 데이터로는 에러가 발생할 가능성 높음 (heuristic 분배의 부정확성)
    assert isinstance(result["reconciliation_errors"], list)


@pytest.mark.asyncio
async def test_e2e_repo_persists_companies_edges_metrics_after_pipeline() -> None:
    """Phase 1 영속화 검증 - repo 에 모든 도메인 객체 누적."""
    graph = build_graph()
    deps = _make_realistic_deps()
    config: dict[str, Any] = {
        "configurable": {"thread_id": "e2e-2", "deps": deps},
    }

    await graph.ainvoke(_initial_state(), config=config)

    # 13개 회사 + 24개 엣지
    assert len(deps.repo.list_companies()) == 13
    assert len(deps.repo.list_edges()) == 24

    # 2024Q3 edge_metrics 는 데이터가 있는 supplier 의 엣지 수만큼 영속화 (17개)
    #  - Samsung(005930.KS) supplier 엣지: NVDA HBM, AMD HBM, INTC DDR5, AAPL MOBILE_DRAM = 4
    #  - SK Hynix(000660.KS) supplier 엣지: NVDA HBM, AMD HBM, INTC DDR5, AAPL MOBILE_DRAM = 4
    #  - Micron(MU) supplier 엣지: NVDA HBM, INTC DDR5, AAPL MOBILE_DRAM = 3
    #  - TSMC(TSM) supplier 엣지: NVDA COWOS, AMD COWOS, INTC 5NM, AAPL 3NM, QCOM 4NM, 2454.TW 4NM = 6
    #  → 4 + 4 + 3 + 6 = 17
    # ASML/AMAT/LRCX supplier 엣지 7개는 fixture 데이터 부재로 hypothesis(revenue=None) → 영속화 X
    metrics_q3 = deps.repo.list_edge_metrics(quarter="2024Q3")
    assert len(metrics_q3) == 17

    # 모든 메트릭이 citation 1개 이상 연결 (Mandatory Grounding)
    for metric in metrics_q3:
        cits = deps.repo.get_metric_citations(metric.id)
        assert cits, f"metric {metric.id} ({metric.edge_id}) has no citations"


@pytest.mark.asyncio
async def test_e2e_trace_events_capture_all_four_agents_in_order() -> None:
    """SSE 스트림 호환성 - 4개 에이전트 모두 agent_complete 이벤트 송출."""
    graph = build_graph()
    deps = _make_realistic_deps()
    config: dict[str, Any] = {
        "configurable": {"thread_id": "e2e-3", "deps": deps},
    }

    result = await graph.ainvoke(_initial_state(), config=config)

    completes = [e for e in result["trace_events"] if e["event_type"] == "agent_complete"]
    agents_in_order = [e["agent"] for e in completes]

    assert agents_in_order == [
        "StructureMapper",
        "DataCollector",
        "QuantEstimator",
        "Evaluator",
    ]

    # pipeline_complete 마커 (UI가 종료 인식용)
    assert any(e["event_type"] == "pipeline_complete" for e in result["trace_events"])


@pytest.mark.asyncio
async def test_e2e_time_isolation_blocks_future_data() -> None:
    """as_of_date 이전 데이터만 통과 - 백테스트 호환성 검증."""
    graph = build_graph()
    deps = _make_realistic_deps()
    state = _initial_state()
    # as_of_date = 2024-09-30: DART 공시(2024-11-14)는 제외, EDGAR(2024-09-30)은 통과
    state["as_of_date"] = datetime(2024, 9, 30, 23, 59, 59, tzinfo=UTC)
    config: dict[str, Any] = {
        "configurable": {"thread_id": "e2e-time-iso", "deps": deps},
    }

    result = await graph.ainvoke(state, config=config)

    facts = result["raw_data"]["facts_by_ticker"]
    # KR 공시는 차단됨
    assert "000660.KS" not in facts
    assert "005930.KS" not in facts
    # US 공시는 통과
    assert "MU" in facts
    assert "NVDA" in facts

    # 시점격리 카운터 증가
    assert result["raw_data"]["stats"]["facts_isolated_by_time"] > 0
