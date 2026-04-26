"""SEC EDGAR XBRL Company Facts API.

API 문서: https://www.sec.gov/edgar/sec-api-documentation
인증: 불필요. User-Agent (이메일 포함) 필수.
Rate limit: 10 req/sec
"""

from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.sources.types import EdgarFinancialFact, SourceCitation


class EdgarClientError(Exception):
    """EDGAR API 호출 실패."""


class EdgarClient:
    """SEC EDGAR 비동기 클라이언트."""

    BASE_URL = "https://data.sec.gov"

    KNOWN_CIKS: dict[str, str] = {
        "MU": "0000723125",
        "NVDA": "0001045810",
        "AMD": "0000002488",
        "INTC": "0000050863",
        "TSM": "0001046179",
    }

    def __init__(self, user_agent: str, *, timeout: float = 30.0) -> None:
        if "@" not in user_agent:
            raise EdgarClientError("SEC requires User-Agent with email contact")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    async def __aenter__(self) -> "EdgarClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        """전체 XBRL facts (us-gaap:Revenues, us-gaap:CostOfRevenue 등 포함)."""
        cik_padded = cik.lstrip("0").zfill(10)
        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def extract_quarterly(
        self,
        facts: dict[str, Any],
        concept: str,
        ticker: str,
    ) -> list[EdgarFinancialFact]:
        """us-gaap:Revenues 등의 분기 값 추출 (10-Q form만).

        XBRL 응답 구조:
            facts.facts['us-gaap'][concept]['units']['USD'] = [
                {'val': N, 'fy': 2024, 'fp': 'Q3', 'form': '10-Q', ...}, ...
            ]
        """
        try:
            entries = facts["facts"]["us-gaap"][concept]["units"]["USD"]
        except KeyError:
            return []

        cik = facts.get("cik", "")
        company_name = facts.get("entityName", "")
        results: list[EdgarFinancialFact] = []
        for entry in entries:
            if entry.get("form") != "10-Q":
                continue
            fy = entry.get("fy")
            fp = entry.get("fp")  # 'Q1', 'Q2', 'Q3'
            if not (isinstance(fy, int) and fp in ("Q1", "Q2", "Q3", "FY")):
                continue
            quarter = f"{fy}{fp}" if fp != "FY" else f"{fy}Q4"
            accn = entry.get("accn", "")
            citation = SourceCitation(
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-Q",  # type: ignore[arg-type]
                source_type="EDGAR",
                source_tier=1,
                publish_date=date.fromisoformat(entry.get("filed", str(date.today()))),
                disclosure_id=accn,
                snippet=f"{company_name} - {concept} - {entry.get('val')}",
            )
            results.append(
                EdgarFinancialFact(
                    company_ticker=ticker,
                    quarter=quarter,
                    metric_name="revenue" if "Revenue" in concept else "cogs",
                    value=float(entry["val"]),
                    currency="USD",
                    cik=cik if isinstance(cik, str) else str(cik),
                    concept=concept,
                    form_type="10-Q",
                    citation=citation,
                )
            )
        return results
