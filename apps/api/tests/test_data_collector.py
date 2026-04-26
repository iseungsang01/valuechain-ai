"""T2.3 - DataCollector 노드 통합 검증.

Mock 어댑터 + InMemoryRepository 조합으로 외부 API 호출 없이 검증.
"""

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.agents.deps import PipelineDeps
from app.agents.nodes.data_collector import data_collection_node
from app.agents.state import PipelineState
from app.agents.topology import MEMORY_SEMICONDUCTOR_TOPOLOGY
from app.db.repository import InMemoryRepository
from app.sources.types import (
    DartFinancialFact,
    EdgarFinancialFact,
    SourceCitation,
)

# ============================================================
# Mock 어댑터
# ============================================================


class _MockDartClient:
    """KR 회사 매출/COGS 응답 stub. corp_code -> facts 매핑."""

    def __init__(self, fixtures: dict[str, list[DartFinancialFact]]) -> None:
        self.fixtures = fixtures
        self.calls: list[dict[str, Any]] = []

    async def get_quarterly_revenue_cogs(
        self,
        *,
        corp_code: str,
        year: int,
        reprt_code: str,
        ticker: str = "",
    ) -> list[DartFinancialFact]:
        self.calls.append(
            {
                "corp_code": corp_code,
                "year": year,
                "reprt_code": reprt_code,
                "ticker": ticker,
            }
        )
        return self.fixtures.get(corp_code, [])


class _MockEdgarClient:
    """US 회사 응답 stub. cik -> facts 매핑."""

    def __init__(
        self,
        rev_fixtures: dict[str, list[EdgarFinancialFact]],
        cogs_fixtures: dict[str, list[EdgarFinancialFact]] | None = None,
    ) -> None:
        self.rev_fixtures = rev_fixtures
        self.cogs_fixtures = cogs_fixtures or {}
        self.facts_calls: list[str] = []

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        self.facts_calls.append(cik)
        return {"_cik_marker": cik}

    def extract_quarterly(
        self,
        facts: dict[str, Any],
        concept: str,
        ticker: str,  # noqa: ARG002 - 인터페이스 매칭용
    ) -> list[EdgarFinancialFact]:
        cik = facts.get("_cik_marker", "")
        if "Revenue" in concept:
            return self.rev_fixtures.get(cik, [])
        return self.cogs_fixtures.get(cik, [])


def _make_dart_factory(fixtures: dict[str, list[DartFinancialFact]]) -> Any:
    @asynccontextmanager
    async def factory():
        yield _MockDartClient(fixtures)

    return factory


def _make_edgar_factory(
    rev: dict[str, list[EdgarFinancialFact]],
    cogs: dict[str, list[EdgarFinancialFact]] | None = None,
) -> Any:
    @asynccontextmanager
    async def factory():
        yield _MockEdgarClient(rev, cogs)

    return factory


# ============================================================
# 픽스처 빌더
# ============================================================


def _dart_fact(
    corp_code: str,
    ticker: str,
    quarter: str,
    metric: str,
    value: float,
    publish: date,
    rcept_no: str = "20241114000123",
) -> DartFinancialFact:
    return DartFinancialFact(
        company_ticker=ticker,
        quarter=quarter,
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
    quarter: str,
    metric: str,
    value: float,
    publish: date,
    accn: str = "0000723125-24-000074",
) -> EdgarFinancialFact:
    return EdgarFinancialFact(
        company_ticker=ticker,
        quarter=quarter,
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


def _initial_state(
    target_quarter: str = "2024Q3",
    as_of_date: datetime | None = None,
) -> PipelineState:
    return PipelineState(
        sector="memory_semiconductor",
        target_quarter=target_quarter,
        as_of_date=as_of_date or datetime(2024, 11, 30, tzinfo=UTC),
        is_backtest=False,
        run_id=None,
        topology=dict(MEMORY_SEMICONDUCTOR_TOPOLOGY),
        raw_data=None,
        quantified=None,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )


def _config(deps: PipelineDeps) -> dict[str, Any]:
    return {"configurable": {"deps": deps}}


# ============================================================
# 테스트 - 정상 흐름
# ============================================================


@pytest.mark.asyncio
async def test_collector_upserts_companies_and_edges() -> None:
    """토폴로지 7개 회사 + 11개 엣지가 repo 에 모두 들어감."""
    repo = InMemoryRepository()
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory({}),
        edgar_factory=_make_edgar_factory({}),
    )

    await data_collection_node(_initial_state(), _config(deps))

    assert len(repo.list_companies()) == 7
    assert len(repo.list_edges()) == 11


@pytest.mark.asyncio
async def test_collector_populates_raw_data_with_dart_and_edgar_facts() -> None:
    """KR 회사는 DART, US/TW 회사는 EDGAR 호출 후 facts 누적."""
    repo = InMemoryRepository()
    dart_fixtures = {
        "00164779": [  # SK Hynix
            _dart_fact("00164779", "000660.KS", "2024Q3", "revenue", 17_500_000_000_000.0, date(2024, 11, 14)),
            _dart_fact("00164779", "000660.KS", "2024Q3", "cogs", 9_800_000_000_000.0, date(2024, 11, 14)),
        ],
        "00126380": [  # Samsung
            _dart_fact("00126380", "005930.KS", "2024Q3", "revenue", 79_000_000_000_000.0, date(2024, 10, 31)),
        ],
    }
    edgar_rev = {
        "0000723125": [  # Micron
            _edgar_fact("0000723125", "MU", "2024Q3", "revenue", 7_750_000_000.0, date(2024, 6, 26)),
        ],
        "0001045810": [  # NVIDIA
            _edgar_fact("0001045810", "NVDA", "2024Q3", "revenue", 30_000_000_000.0, date(2024, 8, 28)),
        ],
    }

    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory(dart_fixtures),
        edgar_factory=_make_edgar_factory(edgar_rev),
    )

    result = await data_collection_node(_initial_state(), _config(deps))

    raw_data = result["raw_data"]
    assert raw_data is not None

    facts = raw_data["facts_by_ticker"]
    assert "000660.KS" in facts
    assert "005930.KS" in facts
    assert "MU" in facts
    assert "NVDA" in facts

    sk_facts = facts["000660.KS"]
    sk_metrics = {f["metric_name"] for f in sk_facts}
    assert sk_metrics == {"revenue", "cogs"}

    # 모든 facts 가 citation_id 첨부
    for ticker_facts in facts.values():
        for f in ticker_facts:
            assert f["citation_id"]


@pytest.mark.asyncio
async def test_collector_persists_citations_in_repo() -> None:
    """Mandatory Grounding: 모든 facts 의 citation 이 repo 에 영속화."""
    repo = InMemoryRepository()
    dart_fixtures = {
        "00164779": [
            _dart_fact("00164779", "000660.KS", "2024Q3", "revenue", 17e12, date(2024, 11, 14)),
        ]
    }
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory(dart_fixtures),
        edgar_factory=_make_edgar_factory({}),
    )
    result = await data_collection_node(_initial_state(), _config(deps))

    citation_id_str = result["raw_data"]["facts_by_ticker"]["000660.KS"][0]["citation_id"]
    from uuid import UUID

    citation = repo.get_citation(UUID(citation_id_str))
    assert citation is not None
    assert citation.publish_date == date(2024, 11, 14)


@pytest.mark.asyncio
async def test_collector_dedupes_dart_citation_by_disclosure_id() -> None:
    """동일 rcept_no 의 매출/COGS 는 같은 citation 으로 통합."""
    repo = InMemoryRepository()
    dart_fixtures = {
        "00164779": [
            _dart_fact("00164779", "000660.KS", "2024Q3", "revenue", 17e12, date(2024, 11, 14), rcept_no="DART-001"),
            _dart_fact("00164779", "000660.KS", "2024Q3", "cogs", 9e12, date(2024, 11, 14), rcept_no="DART-001"),
        ]
    }
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory(dart_fixtures),
        edgar_factory=_make_edgar_factory({}),
    )
    result = await data_collection_node(_initial_state(), _config(deps))

    # 두 fact 가 동일 disclosure_id 를 공유하므로 citation 1개만 생성
    facts = result["raw_data"]["facts_by_ticker"]["000660.KS"]
    citation_ids = {f["citation_id"] for f in facts}
    assert len(citation_ids) == 1


# ============================================================
# Time Isolation
# ============================================================


@pytest.mark.asyncio
async def test_collector_filters_facts_published_after_as_of_date() -> None:
    """publish_date > as_of_date 인 fact 는 raw_data 에서 제외."""
    repo = InMemoryRepository()
    # as_of = 2024-09-30, publish = 2024-11-14 (백테스트에선 누설)
    dart_fixtures = {
        "00164779": [
            _dart_fact("00164779", "000660.KS", "2024Q3", "revenue", 17e12, date(2024, 11, 14)),
        ]
    }
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory(dart_fixtures),
        edgar_factory=_make_edgar_factory({}),
    )
    state = _initial_state(
        as_of_date=datetime(2024, 9, 30, tzinfo=UTC)
    )

    result = await data_collection_node(state, _config(deps))

    facts = result["raw_data"]["facts_by_ticker"]
    assert "000660.KS" not in facts
    assert result["raw_data"]["stats"]["facts_isolated_by_time"] == 1


@pytest.mark.asyncio
async def test_collector_keeps_facts_published_on_exact_as_of_date() -> None:
    """publish_date == as_of_date 는 통과 (<= 비교)."""
    repo = InMemoryRepository()
    dart_fixtures = {
        "00164779": [
            _dart_fact("00164779", "000660.KS", "2024Q3", "revenue", 17e12, date(2024, 11, 14)),
        ]
    }
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory(dart_fixtures),
        edgar_factory=_make_edgar_factory({}),
    )
    state = _initial_state(
        as_of_date=datetime(2024, 11, 14, 23, 59, 59, tzinfo=UTC)
    )

    result = await data_collection_node(state, _config(deps))
    assert "000660.KS" in result["raw_data"]["facts_by_ticker"]


# ============================================================
# 에러 + 엣지 케이스
# ============================================================


@pytest.mark.asyncio
async def test_collector_returns_error_event_when_topology_missing() -> None:
    repo = InMemoryRepository()
    deps = PipelineDeps(repo=repo)
    state = _initial_state()
    state["topology"] = None

    result = await data_collection_node(state, _config(deps))

    assert result["raw_data"] is None
    assert any(
        e["event_type"] == "error" for e in result["trace_events"]
    )


@pytest.mark.asyncio
async def test_collector_handles_adapter_exception_per_ticker() -> None:
    """한 회사 호출이 실패해도 다른 회사는 계속 진행."""
    repo = InMemoryRepository()

    @asynccontextmanager
    async def failing_dart_factory():
        class _Failing:
            async def get_quarterly_revenue_cogs(self, **_: object) -> list[DartFinancialFact]:
                raise RuntimeError("DART down")

        yield _Failing()

    edgar_rev = {
        "0001045810": [
            _edgar_fact("0001045810", "NVDA", "2024Q3", "revenue", 30e9, date(2024, 8, 28))
        ]
    }
    deps = PipelineDeps(
        repo=repo,
        dart_factory=failing_dart_factory,
        edgar_factory=_make_edgar_factory(edgar_rev),
    )

    result = await data_collection_node(_initial_state(), _config(deps))

    # NVDA 는 정상 수집
    assert "NVDA" in result["raw_data"]["facts_by_ticker"]
    # 에러 이벤트가 적어도 하나 (DART 실패)
    error_events = [e for e in result["trace_events"] if e["event_type"] == "error"]
    assert error_events
    assert any("DART" in str(e["payload"]) or "RuntimeError" in str(e["payload"]) for e in error_events)


@pytest.mark.asyncio
async def test_collector_with_no_factories_returns_empty_facts_no_crash() -> None:
    """Phase 1 기본 동작: 어댑터 미설정 → 빈 facts 반환, 크래시 없음."""
    repo = InMemoryRepository()
    deps = PipelineDeps(repo=repo)  # factories=None

    result = await data_collection_node(_initial_state(), _config(deps))

    assert result["raw_data"]["facts_by_ticker"] == {}
    # 그래도 companies / edges 는 upsert 됨
    assert len(repo.list_companies()) == 7
    assert len(repo.list_edges()) == 11


@pytest.mark.asyncio
async def test_collector_emits_progress_trace_events() -> None:
    repo = InMemoryRepository()
    deps = PipelineDeps(
        repo=repo,
        dart_factory=_make_dart_factory({}),
        edgar_factory=_make_edgar_factory({}),
    )
    result = await data_collection_node(_initial_state(), _config(deps))

    events = result["trace_events"]
    assert events[0]["event_type"] == "agent_start"
    assert any(e["event_type"] == "graph_update" for e in events)
    assert events[-1]["event_type"] == "agent_complete"
