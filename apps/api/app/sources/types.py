"""공통 타입 - 어댑터 응답 + citation 메타데이터."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceCitation(BaseModel):
    """모든 어댑터가 반환하는 citation 메타데이터.

    DB의 citations 테이블과 1:1 매핑.
    """

    source_url: HttpUrl
    source_type: Literal["DART", "EDGAR", "CUSTOMS", "IR_PDF", "NEWS", "EARNINGS_CALL"]
    source_tier: Literal[1, 2, 3]
    publish_date: date
    disclosure_id: str | None = None
    snippet: str | None = None


class FinancialFactBase(BaseModel):
    """공시 단일 fact (분기 매출/COGS 등) 공통 필드."""

    company_ticker: str
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")
    metric_name: str  # 'revenue', 'cogs' 등
    value: float
    currency: Literal["USD", "KRW", "JPY", "TWD", "CNY"]
    citation: SourceCitation


class DartFinancialFact(FinancialFactBase):
    """DART 사업/분기보고서에서 추출한 단일 fact."""

    corp_code: str
    reprt_code: Literal["11013", "11012", "11014", "11011"]  # 1Q/반기/3Q/사업


class EdgarFinancialFact(FinancialFactBase):
    """SEC EDGAR XBRL에서 추출한 단일 fact."""

    cik: str
    concept: str  # 'us-gaap:Revenues' 등
    form_type: Literal["10-K", "10-Q", "8-K"]


class FxRate(BaseModel):
    """분기 평균 환율."""

    currency_pair: str = Field(pattern=r"^[A-Z]{3}/[A-Z]{3}$")
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")
    rate: float = Field(gt=0)
    citation: SourceCitation
