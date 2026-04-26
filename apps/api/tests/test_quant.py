"""T2.5 - QuantEstimator + imputation 검증."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.agents.deps import PipelineDeps
from app.agents.nodes.quant_estimator import quantification_node
from app.agents.state import PipelineState
from app.agents.topology import MEMORY_SEMICONDUCTOR_TOPOLOGY
from app.db.repository import InMemoryRepository
from app.services.imputation import (
    DEFAULT_PRODUCT_SHARE,
    PRODUCT_REVENUE_SHARE,
    get_product_share,
    impute_edge_revenue,
    to_usd,
)

# ============================================================
# imputation 단위 테스트
# ============================================================


def test_get_product_share_known() -> None:
    assert get_product_share("HBM") == PRODUCT_REVENUE_SHARE["HBM"]
    assert get_product_share("DRAM_DDR5") == PRODUCT_REVENUE_SHARE["DRAM_DDR5"]


def test_get_product_share_unknown_falls_back() -> None:
    assert get_product_share("EXOTIC_PRODUCT") == DEFAULT_PRODUCT_SHARE


def test_to_usd_passthrough_for_usd() -> None:
    assert to_usd(100.0, "USD", {}, "2024Q3") == 100.0


def test_to_usd_converts_krw() -> None:
    # 1 USD = 1300 KRW
    rates = {("KRW/USD", "2024Q3"): 1300.0}
    # 1,300,000 KRW = 1000 USD
    assert to_usd(1_300_000, "KRW", rates, "2024Q3") == pytest.approx(1000.0)


def test_to_usd_missing_rate_returns_original() -> None:
    """Phase 1 fallback: 환율 없으면 원본값 반환 (호출자가 별도 경고)."""
    assert to_usd(1_300_000, "KRW", {}, "2024Q3") == 1_300_000


def test_impute_edge_revenue_distributes_across_buyers() -> None:
    """공급사 매출 × HBM 비중 ÷ 바이어 수."""
    rev = impute_edge_revenue(
        supplier_total_revenue_usd=10_000_000_000.0,
        product_category="HBM",
        n_buyers_for_product=3,  # NVIDIA, AMD, ?
    )
    expected = 10_000_000_000.0 * PRODUCT_REVENUE_SHARE["HBM"] / 3
    assert rev == pytest.approx(expected)


def test_impute_edge_revenue_zero_buyers_returns_zero() -> None:
    assert (
        impute_edge_revenue(
            supplier_total_revenue_usd=1.0,
            product_category="HBM",
            n_buyers_for_product=0,
        )
        == 0.0
    )


# ============================================================
# 통합 테스트 - 노드
# ============================================================


def _initial_state(
    raw_data: dict[str, Any] | None = None,
    target_quarter: str = "2024Q3",
) -> PipelineState:
    return PipelineState(
        sector="memory_semiconductor",
        target_quarter=target_quarter,
        as_of_date=datetime(2024, 11, 30, tzinfo=UTC),
        is_backtest=False,
        run_id=None,
        topology=dict(MEMORY_SEMICONDUCTOR_TOPOLOGY),
        raw_data=raw_data,
        quantified=None,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )


def _config(deps: PipelineDeps) -> dict[str, Any]:
    return {"configurable": {"deps": deps}}


def _setup_repo_with_companies_and_edges(repo: InMemoryRepository) -> tuple[dict[str, str], dict[str, str]]:
    """Quant 노드는 DataCollector 가 이미 채운 상태를 가정하므로
    repo 와 raw_data['edge_ids'] 를 미리 세팅."""
    company_ids: dict[str, str] = {}
    for node in MEMORY_SEMICONDUCTOR_TOPOLOGY["nodes"]:
        rec = repo.upsert_company(
            ticker=node["ticker"],
            name=node["name"],
            country=node["country"],
            sector=node["sector"],
        )
        company_ids[node["ticker"]] = str(rec.id)

    edge_ids: dict[str, str] = {}
    for edge in MEMORY_SEMICONDUCTOR_TOPOLOGY["edges"]:
        rec = repo.get_or_create_edge(
            supplier_id=UUID(company_ids[edge["supplier_ticker"]]),
            buyer_id=UUID(company_ids[edge["buyer_ticker"]]),
            product_category=edge["product_category"],
            lag_quarters=edge["lag_quarters"],
        )
        key = f"{edge['supplier_ticker']}->{edge['buyer_ticker']}|{edge['product_category']}"
        edge_ids[key] = str(rec.id)
    return company_ids, edge_ids


def _make_citation(repo: InMemoryRepository, publish_iso: str = "2024-11-14") -> str:
    """Stub citation - publish 날짜만 중요."""
    from datetime import date as _date

    from app.sources.types import SourceCitation

    cit = SourceCitation(
        source_url="https://example.test/citation",  # type: ignore[arg-type]
        source_type="DART",
        source_tier=1,
        publish_date=_date.fromisoformat(publish_iso),
        disclosure_id=f"STUB-{publish_iso}-{id(repo)}",  # uniqueness
    )
    return str(repo.upsert_citation(cit).id)


@pytest.mark.asyncio
async def test_quant_distributes_supplier_revenue_across_edges() -> None:
    """SK Hynix 매출이 NVIDIA + AMD HBM 엣지로 균등 분배."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)

    raw_data = {
        "company_ids": {},
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "000660.KS": [
                {
                    "metric_name": "revenue",
                    "value": 17_500_000_000_000.0,  # 17.5조 KRW
                    "currency": "KRW",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"000660.KS": [cit_id]},
        "stats": {},
    }

    deps = PipelineDeps(
        repo=repo,
        fx_rates={("KRW/USD", "2024Q3"): 1340.0},
    )
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    quantified = result["quantified"]
    assert quantified is not None

    # SK Hynix 의 두 HBM 엣지 (NVIDIA, AMD)
    sk_hbm_edges = [
        m
        for m in quantified["edge_metrics"]
        if m["supplier_ticker"] == "000660.KS" and m["product_category"] == "HBM"
    ]
    assert len(sk_hbm_edges) == 2  # NVIDIA + AMD

    # 두 엣지의 매출은 동일해야 함 (균등 분배)
    rev1 = sk_hbm_edges[0]["revenue_usd"]
    rev2 = sk_hbm_edges[1]["revenue_usd"]
    assert rev1 == pytest.approx(rev2)
    # 합계 ≈ 매출 × HBM 비중
    expected_total_hbm = (17_500_000_000_000.0 / 1340.0) * PRODUCT_REVENUE_SHARE["HBM"]
    assert rev1 + rev2 == pytest.approx(expected_total_hbm)


@pytest.mark.asyncio
async def test_quant_currency_conversion_krw_to_usd() -> None:
    """KRW 매출이 FX rate 로 정확히 USD 환산."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)

    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "000660.KS": [
                {
                    "metric_name": "revenue",
                    "value": 13_400_000_000_000.0,  # 13.4조 KRW
                    "currency": "KRW",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"000660.KS": [cit_id]},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(
        repo=repo,
        fx_rates={("KRW/USD", "2024Q3"): 1340.0},
    )
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    quantified = result["quantified"]
    # 13.4조 KRW / 1340 = 10B USD
    assert quantified["supplier_revenue_usd"]["000660.KS"] == pytest.approx(10_000_000_000.0)


@pytest.mark.asyncio
async def test_quant_marks_imputed_metrics() -> None:
    """모든 Phase 1 엣지 매출은 is_imputed=True."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)
    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "MU": [
                {
                    "metric_name": "revenue",
                    "value": 7_750_000_000.0,
                    "currency": "USD",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"MU": [cit_id]},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(repo=repo)
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    mu_edges = [
        m for m in result["quantified"]["edge_metrics"] if m["supplier_ticker"] == "MU"
    ]
    assert mu_edges
    for m in mu_edges:
        if m["revenue_usd"] is not None:
            assert m["is_imputed"] is True


@pytest.mark.asyncio
async def test_quant_writes_edge_metrics_to_repo_with_citations() -> None:
    """Mandatory Grounding: 모든 metric 이 citation 에 연결."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)
    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "MU": [
                {
                    "metric_name": "revenue",
                    "value": 7_750_000_000.0,
                    "currency": "USD",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"MU": [cit_id]},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(repo=repo)
    await quantification_node(_initial_state(raw_data), _config(deps))

    metrics_in_repo = repo.list_edge_metrics(quarter="2024Q3")
    assert metrics_in_repo  # MU 가 공급하는 엣지 (NVDA HBM, INTC DRAM_DDR5)

    # 모든 영속화된 metric 이 citation 1개 이상 연결
    for metric in metrics_in_repo:
        if metric.revenue is not None:
            cits = repo.get_metric_citations(metric.id)
            assert cits, f"metric {metric.id} has no citations"


@pytest.mark.asyncio
async def test_quant_handles_supplier_without_revenue_data() -> None:
    """매출 데이터 없는 공급사 → hypothesis only, revenue_usd=None."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {},  # 어떤 회사도 매출 없음
        "citation_ids_by_ticker": {},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(repo=repo)
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    edge_metrics = result["quantified"]["edge_metrics"]
    assert edge_metrics  # 엣지 정의는 11개, 모두 hypothesis 로 등장
    assert all(m["revenue_usd"] is None for m in edge_metrics)
    assert all(m["is_hypothesis"] is True for m in edge_metrics)


@pytest.mark.asyncio
async def test_quant_returns_error_when_raw_data_missing() -> None:
    repo = InMemoryRepository()
    deps = PipelineDeps(repo=repo)
    result = await quantification_node(_initial_state(raw_data=None), _config(deps))

    assert result["quantified"] is None
    assert any(e["event_type"] == "error" for e in result["trace_events"])


@pytest.mark.asyncio
async def test_quant_emits_fx_warning_when_rate_missing() -> None:
    """KRW 매출인데 FX rate 미설정 시 경고 이벤트."""
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)
    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "000660.KS": [
                {
                    "metric_name": "revenue",
                    "value": 17e12,
                    "currency": "KRW",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"000660.KS": [cit_id]},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(repo=repo, fx_rates={})  # no rates
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    fx_warning_events = [
        e
        for e in result["trace_events"]
        if e["event_type"] == "thought" and "fx_warnings" in e["payload"]
    ]
    assert fx_warning_events


@pytest.mark.asyncio
async def test_quant_populates_confidence_map() -> None:
    repo = InMemoryRepository()
    _, edge_ids = _setup_repo_with_companies_and_edges(repo)
    cit_id = _make_citation(repo)
    raw_data = {
        "edge_ids": edge_ids,
        "facts_by_ticker": {
            "MU": [
                {
                    "metric_name": "revenue",
                    "value": 7e9,
                    "currency": "USD",
                    "quarter": "2024Q3",
                    "citation_id": cit_id,
                }
            ]
        },
        "citation_ids_by_ticker": {"MU": [cit_id]},
        "company_ids": {},
        "stats": {},
    }
    deps = PipelineDeps(repo=repo)
    result = await quantification_node(_initial_state(raw_data), _config(deps))

    confidence_map = result["confidence_map"]
    # MU 엣지가 confidence_map 에 포함
    mu_keys = [k for k in confidence_map if k.startswith("MU->")]
    assert mu_keys
    for k in mu_keys:
        assert 1 <= confidence_map[k] <= 100
