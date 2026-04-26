"""한국은행 ECOS API 클라이언트 (환율).

API 문서: https://ecos.bok.or.kr
키 발급: 무료, 가입 후 발급
통계코드: 731Y004 (원/달러 환율)
"""

from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.sources.types import FxRate, SourceCitation


class EcosClientError(Exception):
    """ECOS API 호출 실패."""


class EcosClient:
    """한국은행 ECOS 환율 API."""

    BASE_URL = "https://ecos.bok.or.kr/api"

    # 731Y004: 한국 원/달러 환율 (BOK 기준)
    # 110000 = 매매기준율 (영업일 평균)
    USD_KRW_STAT_CODE = "731Y004"
    USD_KRW_ITEM_CODE = "0000001"

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        if not api_key:
            raise EcosClientError("ECOS_API_KEY is required")
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "EcosClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    @staticmethod
    def _quarter_to_dates(quarter: str) -> tuple[str, str]:
        """'2024Q3' -> ('20240701', '20240930')"""
        year = int(quarter[:4])
        q = int(quarter[-1])
        starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
        ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        sm, sd = starts[q]
        em, ed = ends[q]
        return (f"{year}{sm:02d}{sd:02d}", f"{year}{em:02d}{ed:02d}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _fetch_rates(self, url: str) -> dict[str, Any]:
        """HTTP 호출만 retry. 검증 에러는 retry 안 함."""
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_quarterly_average(
        self, currency_pair: str, quarter: str
    ) -> FxRate:
        """분기 영업일 환율의 평균 산출.

        Args:
            currency_pair: 'KRW/USD' (1 USD가 KRW로 얼마)
            quarter: '2024Q3' 형식

        Returns:
            FxRate with citation
        """
        # 검증은 retry 외부 (잘못된 입력에 retry 의미 없음)
        if currency_pair != "KRW/USD":
            raise EcosClientError(f"Phase 1 supports KRW/USD only, got {currency_pair}")

        start, end = self._quarter_to_dates(quarter)
        url = (
            f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/100/"
            f"{self.USD_KRW_STAT_CODE}/D/{start}/{end}/{self.USD_KRW_ITEM_CODE}"
        )

        data = await self._fetch_rates(url)

        rows = data.get("StatisticSearch", {}).get("row", [])
        if not rows:
            raise EcosClientError(f"No FX data for {quarter}")

        rates = [float(row["DATA_VALUE"]) for row in rows if row.get("DATA_VALUE")]
        if not rates:
            raise EcosClientError(f"All FX values empty for {quarter}")

        avg_rate = sum(rates) / len(rates)

        citation = SourceCitation(
            source_url=f"https://ecos.bok.or.kr/api/StatisticSearch/{self.USD_KRW_STAT_CODE}",  # type: ignore[arg-type]
            source_type="CUSTOMS",  # 정부 공식 통계 (Tier 1)
            source_tier=1,
            publish_date=date.today(),
            snippet=f"BOK ECOS {self.USD_KRW_STAT_CODE} {quarter} 평균 ({len(rates)} 영업일)",
        )

        return FxRate(
            currency_pair=currency_pair,
            quarter=quarter,
            rate=avg_rate,
            citation=citation,
        )
