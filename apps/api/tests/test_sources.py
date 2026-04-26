"""DART/EDGAR/ECOS 어댑터 단위 테스트 (mocked HTTP).

실제 API 호출 없이 응답 파싱 + citation 첨부 로직만 검증.
실 API 통합 테스트는 사용자가 키 발급 후 별도 마커로 실행.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.sources.dart import DartClient, DartClientError
from app.sources.edgar import EdgarClient, EdgarClientError
from app.sources.fx import EcosClient, EcosClientError
from app.sources.types import (
    SourceCitation,
)

# ============================================================
# DART
# ============================================================


def test_dart_requires_api_key() -> None:
    with pytest.raises(DartClientError, match="DART_API_KEY"):
        DartClient(api_key="")


@pytest.mark.asyncio
async def test_dart_parses_revenue_and_cogs() -> None:
    """DART 응답 -> DartFinancialFact 변환 검증."""
    mock_response = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "rcept_no": "20241114000123",
                "account_id": "ifrs-full_Revenue",
                "thstrm_amount": "12,500,000,000,000",
                "fs_nm": "연결재무제표",
            },
            {
                "rcept_no": "20241114000123",
                "account_id": "ifrs-full_CostOfSales",
                "thstrm_amount": "8,300,000,000,000",
            },
            # 다른 계정은 무시되어야 함
            {
                "rcept_no": "20241114000123",
                "account_id": "ifrs-full_OperatingIncome",
                "thstrm_amount": "1,000,000,000,000",
            },
        ],
    }

    client = DartClient(api_key="dummy")
    with patch.object(client, "_request", AsyncMock(return_value=mock_response)):
        facts = await client.get_quarterly_revenue_cogs(
            corp_code="00164779",
            year=2024,
            reprt_code="11014",
            ticker="000660.KS",
        )

    assert len(facts) == 2  # revenue + cogs (operating income 제외)
    revenue = next(f for f in facts if f.metric_name == "revenue")
    cogs = next(f for f in facts if f.metric_name == "cogs")
    assert revenue.value == 12_500_000_000_000
    assert cogs.value == 8_300_000_000_000
    assert revenue.currency == "KRW"
    assert revenue.quarter == "2024Q3"
    assert revenue.citation.source_type == "DART"
    assert revenue.citation.source_tier == 1
    assert revenue.citation.disclosure_id == "20241114000123"


# ============================================================
# EDGAR
# ============================================================


def test_edgar_requires_user_agent_with_email() -> None:
    with pytest.raises(EdgarClientError, match="email"):
        EdgarClient(user_agent="ValueChain")


def test_edgar_extracts_quarterly_facts() -> None:
    """XBRL companyfacts -> EdgarFinancialFact 변환 검증."""
    mock_facts = {
        "cik": "0000723125",
        "entityName": "Micron Technology",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 7750000000,
                                "fy": 2024,
                                "fp": "Q3",
                                "form": "10-Q",
                                "filed": "2024-06-26",
                                "accn": "0000723125-24-000074",
                            },
                            {
                                "val": 5800000000,
                                "fy": 2024,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2024-03-20",
                                "accn": "0000723125-24-000050",
                            },
                            # 10-K는 무시
                            {
                                "val": 25000000000,
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2023-10-13",
                                "accn": "0000723125-23-000080",
                            },
                        ]
                    }
                }
            }
        },
    }

    client = EdgarClient(user_agent="Test test@example.com")
    facts = client.extract_quarterly(mock_facts, "Revenues", ticker="MU")

    # 10-K 제외 = 2개
    assert len(facts) == 2
    q3 = next(f for f in facts if f.quarter == "2024Q3")
    assert q3.value == 7_750_000_000
    assert q3.currency == "USD"
    assert q3.citation.disclosure_id == "0000723125-24-000074"
    assert q3.citation.publish_date == date(2024, 6, 26)


# ============================================================
# ECOS (FX)
# ============================================================


def test_ecos_requires_api_key() -> None:
    with pytest.raises(EcosClientError, match="ECOS_API_KEY"):
        EcosClient(api_key="")


def test_ecos_quarter_to_dates() -> None:
    """분기 -> 시작/종료일 변환."""
    assert EcosClient._quarter_to_dates("2024Q1") == ("20240101", "20240331")
    assert EcosClient._quarter_to_dates("2024Q3") == ("20240701", "20240930")
    assert EcosClient._quarter_to_dates("2024Q4") == ("20241001", "20241231")


@pytest.mark.asyncio
async def test_ecos_calculates_quarterly_average() -> None:
    """일별 환율 응답 -> 분기 평균 계산."""
    mock_response = {
        "StatisticSearch": {
            "row": [
                {"TIME": "20240701", "DATA_VALUE": "1380.5"},
                {"TIME": "20240702", "DATA_VALUE": "1378.2"},
                {"TIME": "20240703", "DATA_VALUE": "1382.8"},
            ]
        }
    }

    client = EcosClient(api_key="dummy")
    with patch.object(client, "_fetch_rates", AsyncMock(return_value=mock_response)):
        result = await client.get_quarterly_average("KRW/USD", "2024Q3")

    expected_avg = (1380.5 + 1378.2 + 1382.8) / 3
    assert result.rate == pytest.approx(expected_avg, rel=1e-4)
    assert result.currency_pair == "KRW/USD"
    assert result.quarter == "2024Q3"
    assert result.citation.source_tier == 1


@pytest.mark.asyncio
async def test_ecos_only_supports_krw_usd_in_phase1() -> None:
    """Phase 1은 KRW/USD만 지원 - retry 외부에서 즉시 raise."""
    client = EcosClient(api_key="dummy")
    with pytest.raises(EcosClientError, match="KRW/USD"):
        await client.get_quarterly_average("JPY/USD", "2024Q3")


# ============================================================
# Types - SourceCitation 검증
# ============================================================


def test_source_citation_validates_tier() -> None:
    """tier는 1~3만 허용."""
    from pydantic import ValidationError

    valid = SourceCitation(
        source_url="https://dart.fss.or.kr/test",  # type: ignore[arg-type]
        source_type="DART",
        source_tier=1,
        publish_date=date.today(),
    )
    assert valid.source_tier == 1

    with pytest.raises(ValidationError):
        SourceCitation(
            source_url="https://dart.fss.or.kr/test",  # type: ignore[arg-type]
            source_type="DART",
            source_tier=4,  # invalid
            publish_date=date.today(),
        )
