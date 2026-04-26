"""DataCollector 노드 - 토폴로지 회사 → DART/EDGAR 호출 → 정합성 입력 준비.

T2.3 책임 범위:
1. 토폴로지의 각 회사를 repo 에 upsert
2. 각 엣지를 repo 에 upsert (edge_id 매핑 확보)
3. 각 회사의 매출/COGS 를 외부 API 로 조회 (DART for KR, EDGAR for US/TW)
4. 시점 격리: citation.publish_date <= as_of_date 만 통과
5. citation 들을 repo 에 upsert
6. state["raw_data"] 에 다음 구조 채움:
   {
     "company_ids": {ticker: uuid_str},
     "edge_ids": {(supplier_ticker, buyer_ticker, product): uuid_str},
     "facts_by_ticker": {ticker: [{"metric_name", "value", "currency", "citation_id"}]},
     "citation_ids_by_ticker": {ticker: [uuid_str]},
   }

edge_metrics 테이블 작성은 QuantEstimator (T2.5) 에서 처리한다 (P×Q 계산 후).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from app.agents.deps import deps_from_config
from app.agents.nodes._trace import emit
from app.agents.state import PipelineState
from app.sources.types import FinancialFactBase


def _is_kr_ticker(country: str) -> bool:
    return country == "KR"


async def _collect_kr_facts(
    factory: Any, ticker: str, corp_code: str, year: int, reprt_code: str
) -> list[FinancialFactBase]:
    """DART 어댑터 호출 wrapper. factory 미설정 시 빈 리스트."""
    if factory is None:
        return []
    async with factory() as client:
        facts = await client.get_quarterly_revenue_cogs(
            corp_code=corp_code,
            year=year,
            reprt_code=reprt_code,
            ticker=ticker,
        )
        return list(facts)


async def _collect_us_facts(
    factory: Any, ticker: str, cik: str, target_quarter: str
) -> list[FinancialFactBase]:
    """EDGAR 어댑터 호출 wrapper - 분기 단위로 필터링."""
    if factory is None:
        return []
    async with factory() as client:
        company_facts = await client.get_company_facts(cik)
    # us-gaap:Revenues + us-gaap:CostOfRevenue 두 concept 모두 추출
    revenues = client.extract_quarterly(company_facts, "Revenues", ticker=ticker)
    # CostOfRevenue concept 명은 회사마다 다를 수 있음. 빈 결과는 무시
    cogs = client.extract_quarterly(company_facts, "CostOfRevenue", ticker=ticker)
    all_facts = revenues + cogs
    return [f for f in all_facts if f.quarter == target_quarter]


def _quarter_to_year_reprt(target_quarter: str) -> tuple[int, str]:
    """'2024Q3' -> (2024, '11014')"""
    year = int(target_quarter[:4])
    q = target_quarter[-1]
    reprt = {"1": "11013", "2": "11012", "3": "11014", "4": "11011"}[q]
    return year, reprt


async def data_collection_node(
    state: PipelineState, config: RunnableConfig
) -> dict[str, Any]:
    """토폴로지 → 외부 API → raw_data 채움 + repo 영속화."""
    deps = deps_from_config(config)
    repo = deps.repo
    topology = state.get("topology")
    target_quarter = state.get("target_quarter", "")
    as_of_date = state.get("as_of_date")

    if topology is None or not target_quarter:
        return {
            "raw_data": None,
            "trace_events": [
                emit(
                    "DataCollector",
                    "error",
                    {"reason": "missing_topology_or_quarter"},
                ),
            ],
        }

    events: list[dict[str, Any]] = [
        emit("DataCollector", "agent_start", {"target_quarter": target_quarter})
    ]

    # 1. Companies upsert
    company_ids: dict[str, str] = {}
    for node in topology["nodes"]:
        rec = repo.upsert_company(
            ticker=node["ticker"],
            name=node["name"],
            country=node["country"],
            sector=node["sector"],
        )
        company_ids[node["ticker"]] = str(rec.id)
    events.append(
        emit(
            "DataCollector",
            "graph_update",
            {"action": "companies_upserted", "count": len(company_ids)},
        )
    )

    # 2. Edges upsert
    edge_ids: dict[str, str] = {}  # JSON-serialisable string key
    for edge in topology["edges"]:
        supplier_id = UUID(company_ids[edge["supplier_ticker"]])
        buyer_id = UUID(company_ids[edge["buyer_ticker"]])
        rec = repo.get_or_create_edge(
            supplier_id=supplier_id,
            buyer_id=buyer_id,
            product_category=edge["product_category"],
            lag_quarters=edge["lag_quarters"],
        )
        key = f"{edge['supplier_ticker']}->{edge['buyer_ticker']}|{edge['product_category']}"
        edge_ids[key] = str(rec.id)
    events.append(
        emit(
            "DataCollector",
            "graph_update",
            {"action": "edges_upserted", "count": len(edge_ids)},
        )
    )

    # 3. Facts 수집 (회사별)
    facts_by_ticker: dict[str, list[dict[str, Any]]] = {}
    citation_ids_by_ticker: dict[str, list[str]] = {}
    year, reprt_code = _quarter_to_year_reprt(target_quarter)
    isolated_facts_count = 0

    for node in topology["nodes"]:
        ticker = node["ticker"]
        country = node["country"]
        events.append(
            emit("DataCollector", "tool_call", {"ticker": ticker, "country": country})
        )

        try:
            if _is_kr_ticker(country):
                from app.sources.dart import DartClient

                corp_code = DartClient.KNOWN_CORP_CODES.get(ticker)
                if not corp_code:
                    facts = []
                else:
                    facts = await _collect_kr_facts(
                        deps.dart_factory, ticker, corp_code, year, reprt_code
                    )
            else:
                from app.sources.edgar import EdgarClient

                cik = EdgarClient.KNOWN_CIKS.get(ticker)
                if not cik:
                    facts = []
                else:
                    facts = await _collect_us_facts(
                        deps.edgar_factory, ticker, cik, target_quarter
                    )
        except Exception as exc:  # noqa: BLE001
            events.append(
                emit(
                    "DataCollector",
                    "error",
                    {"ticker": ticker, "exc": type(exc).__name__, "msg": str(exc)},
                )
            )
            facts = []

        # 4. Time isolation + citation upsert
        ticker_facts: list[dict[str, Any]] = []
        ticker_citations: list[str] = []
        for fact in facts:
            # 시점 격리 (Layer 2)
            if as_of_date is not None and fact.citation.publish_date > as_of_date.date():
                isolated_facts_count += 1
                continue

            citation_rec = repo.upsert_citation(fact.citation)
            ticker_citations.append(str(citation_rec.id))
            ticker_facts.append(
                {
                    "metric_name": fact.metric_name,
                    "value": fact.value,
                    "currency": fact.currency,
                    "quarter": fact.quarter,
                    "citation_id": str(citation_rec.id),
                }
            )

        if ticker_facts:
            facts_by_ticker[ticker] = ticker_facts
            citation_ids_by_ticker[ticker] = ticker_citations
            events.append(
                emit(
                    "DataCollector",
                    "tool_result",
                    {"ticker": ticker, "fact_count": len(ticker_facts)},
                )
            )

    raw_data = {
        "company_ids": company_ids,
        "edge_ids": edge_ids,
        "facts_by_ticker": facts_by_ticker,
        "citation_ids_by_ticker": citation_ids_by_ticker,
        "stats": {
            "tickers_collected": len(facts_by_ticker),
            "tickers_total": len(company_ids),
            "facts_isolated_by_time": isolated_facts_count,
        },
    }

    events.append(
        emit(
            "DataCollector",
            "agent_complete",
            {
                "tickers_with_facts": len(facts_by_ticker),
                "total_facts": sum(len(v) for v in facts_by_ticker.values()),
                "isolated": isolated_facts_count,
            },
        )
    )

    return {"raw_data": raw_data, "trace_events": events}
