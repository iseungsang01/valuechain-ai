"""데모 모드 PipelineDeps 팩토리 - API 키 없이도 시연 가능.

T3.1: SSE 엔드포인트가 .env 의 DART/EDGAR/ECOS 키 없이도
실 데이터 근사값으로 e2e 데모를 보여줄 수 있도록 mock 어댑터를 제공.

실 운영 (API 키 보유) 시:
- create_pipeline_deps(demo=False) → 실 DartClient/EdgarClient/EcosClient 주입
- 현 단계는 demo=True 만 검증.

Phase 2+ 확장: real_dart_factory / real_edgar_factory 분리 + env 분기.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from app.agents.deps import PipelineDeps
from app.db.repository import InMemoryRepository
from app.sources.types import (
    DartFinancialFact,
    EdgarFinancialFact,
    SourceCitation,
)

# ============================================================
# 2024Q3 실 공시 근사값 (메모리 반도체)
# ============================================================
# 출처: SK Hynix/Samsung 분기보고서 + Micron/NVDA/AMD/INTC/TSM 10-Q.
# Phase 1 데모용 - 실제 실사 시점에 갱신.


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


DART_FIXTURES_2024Q3: dict[str, list[DartFinancialFact]] = {
    "00164779": [  # SK Hynix
        _dart_fact("00164779", "000660.KS", "revenue", 17_573_000_000_000.0, "DART-SK-2024Q3"),
        _dart_fact("00164779", "000660.KS", "cogs", 9_840_000_000_000.0, "DART-SK-2024Q3"),
    ],
    "00126380": [  # Samsung Electronics
        _dart_fact("00126380", "005930.KS", "revenue", 79_088_000_000_000.0, "DART-SS-2024Q3"),
        _dart_fact("00126380", "005930.KS", "cogs", 56_220_000_000_000.0, "DART-SS-2024Q3"),
    ],
}

EDGAR_REVENUE_2024Q3: dict[str, list[EdgarFinancialFact]] = {
    "0000723125": [_edgar_fact("0000723125", "MU", "revenue", 7_750_000_000.0, "MU-2024Q3")],
    "0001045810": [_edgar_fact("0001045810", "NVDA", "revenue", 30_040_000_000.0, "NVDA-2024Q3")],
    "0000002488": [_edgar_fact("0000002488", "AMD", "revenue", 6_820_000_000.0, "AMD-2024Q3")],
    "0000050863": [_edgar_fact("0000050863", "INTC", "revenue", 13_280_000_000.0, "INTC-2024Q3")],
    "0001046179": [_edgar_fact("0001046179", "TSM", "revenue", 23_500_000_000.0, "TSM-2024Q3")],
}

EDGAR_COGS_2024Q3: dict[str, list[EdgarFinancialFact]] = {
    "0000723125": [_edgar_fact("0000723125", "MU", "cogs", 5_310_000_000.0, "MU-2024Q3")],
    "0001045810": [_edgar_fact("0001045810", "NVDA", "cogs", 7_660_000_000.0, "NVDA-2024Q3")],
    "0000002488": [_edgar_fact("0000002488", "AMD", "cogs", 3_870_000_000.0, "AMD-2024Q3")],
    "0000050863": [_edgar_fact("0000050863", "INTC", "cogs", 9_950_000_000.0, "INTC-2024Q3")],
    "0001046179": [_edgar_fact("0001046179", "TSM", "cogs", 9_500_000_000.0, "TSM-2024Q3")],
}

# 2024Q3 평균 환율 (BOK ECOS 근사)
DEMO_FX_RATES: dict[tuple[str, str], float] = {
    ("KRW/USD", "2024Q3"): 1340.0,
}


# ============================================================
# Mock 어댑터 - DartClient / EdgarClient 인터페이스 충족
# ============================================================


class _DemoDart:
    """DartClient.get_quarterly_revenue_cogs 시그니처 매칭."""

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


class _DemoEdgar:
    """EdgarClient 인터페이스 충족 (get_company_facts + extract_quarterly)."""

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


# ============================================================
# 데모 PipelineDeps 팩토리
# ============================================================


def build_demo_deps() -> PipelineDeps:
    """API 키 없이 시연 가능한 PipelineDeps.

    InMemoryRepository + 실 공시 근사값 mock 어댑터 + FX rates 정적 주입.
    """

    @asynccontextmanager
    async def dart_factory():  # type: ignore[no-untyped-def]
        yield _DemoDart(DART_FIXTURES_2024Q3)

    @asynccontextmanager
    async def edgar_factory():  # type: ignore[no-untyped-def]
        yield _DemoEdgar(EDGAR_REVENUE_2024Q3, EDGAR_COGS_2024Q3)

    return PipelineDeps(
        repo=InMemoryRepository(),
        dart_factory=dart_factory,
        edgar_factory=edgar_factory,
        fx_rates=dict(DEMO_FX_RATES),
    )
