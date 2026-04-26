"""DART OpenAPI 클라이언트 (한국 전자공시).

API 문서: https://opendart.fss.or.kr
키 발급: 무료, 가입 후 발급
Rate limit: 10,000 호출/일

Phase 1 사용 엔드포인트:
- /fnlttSinglAcntAll.json : 단일회사 전체 재무제표
"""

from datetime import date
from typing import Any, Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.sources.types import DartFinancialFact, SourceCitation


class DartClientError(Exception):
    """DART API 호출 실패."""


# DART 응답 status 코드 의미
DART_STATUS_OK = "000"


class DartClient:
    """DART OpenAPI 비동기 클라이언트.

    사용:
        async with DartClient(api_key="...") as client:
            facts = await client.get_quarterly_revenue_cogs(
                corp_code="00164779", year=2024, reprt_code="11014"
            )
    """

    BASE_URL = "https://opendart.fss.or.kr/api"

    # 메모리 반도체 주요 기업 corp_code (사전 매핑)
    # 실제 운영에선 corpCode.xml zip을 다운받아 매핑하지만,
    # Phase 1 MVP는 하드코드로 충분 (7개 기업 × 1개)
    KNOWN_CORP_CODES: dict[str, str] = {
        "005930.KS": "00126380",  # Samsung Electronics
        "000660.KS": "00164779",  # SK Hynix
    }

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        if not api_key:
            raise DartClientError("DART_API_KEY is required")
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "DartClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _request(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        """공통 GET 요청 + 에러 변환 + 재시도."""
        url = f"{self.BASE_URL}/{endpoint}"
        full_params = {"crtfc_key": self.api_key, **params}
        response = await self._client.get(url, params=full_params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if data.get("status") != DART_STATUS_OK:
            raise DartClientError(
                f"DART error {data.get('status')}: {data.get('message')}"
            )
        return data

    async def get_quarterly_revenue_cogs(
        self,
        corp_code: str,
        year: int,
        reprt_code: Literal["11013", "11012", "11014", "11011"],
        *,
        ticker: str = "",
    ) -> list[DartFinancialFact]:
        """단일회사 분기 재무제표에서 매출/매출원가 추출.

        Args:
            corp_code: 8자리 기업 고유번호 (예: '00164779' = SK하이닉스)
            year: 사업연도 (YYYY)
            reprt_code: 11013=1Q, 11012=반기, 11014=3Q, 11011=사업(연간)

        Returns:
            매출/COGS facts. citation 자동 첨부.
        """
        data = await self._request(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": reprt_code,
                "fs_div": "CFS",  # 연결재무제표
            },
        )

        # rcept_no = 접수번호, 공시 dedup용
        rcept_no = data["list"][0]["rcept_no"] if data.get("list") else ""
        quarter_map = {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "Q4"}
        quarter = f"{year}{quarter_map[reprt_code]}"

        citation = SourceCitation(
            source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",  # type: ignore[arg-type]
            source_type="DART",
            source_tier=1,
            publish_date=date.today(),  # 실제론 응답에서 추출 - V1+ 정밀화
            disclosure_id=rcept_no,
        )

        facts: list[DartFinancialFact] = []
        # 손익계산서에서 매출, 매출원가 추출
        target_metrics = {
            "ifrs-full_Revenue": "revenue",
            "ifrs-full_CostOfSales": "cogs",
        }
        for row in data.get("list", []):
            account_id = row.get("account_id")
            if account_id not in target_metrics:
                continue
            value_str = row.get("thstrm_amount", "0").replace(",", "")
            try:
                value = float(value_str)
            except ValueError:
                continue
            facts.append(
                DartFinancialFact(
                    company_ticker=ticker,
                    quarter=quarter,
                    metric_name=target_metrics[account_id],
                    value=value,
                    currency="KRW",
                    corp_code=corp_code,
                    reprt_code=reprt_code,
                    citation=citation,
                )
            )
        return facts
