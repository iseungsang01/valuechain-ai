"""Data source adapters - DART, EDGAR, ECOS (FX).

각 어댑터는 외부 API 호출 + Pydantic 검증 + citations 메타데이터 첨부.
모든 응답은 GroundedNumber 호환으로 변환 가능해야 함.
"""

from app.sources.types import (
    DartFinancialFact,
    EdgarFinancialFact,
    FxRate,
    SourceCitation,
)

__all__ = [
    "DartFinancialFact",
    "EdgarFinancialFact",
    "FxRate",
    "SourceCitation",
]
