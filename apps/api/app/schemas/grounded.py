"""Mandatory Grounding 스키마 (ADR-005).

3중 방어 중 Layer 1: 출력 스키마 강제.
- 모든 수치(GroundedNumber)는 citation_ids 1개 이상 필수
- 빈 리스트 / 가공 UUID / 시간격리 위반은 후속 validation 단계에서 차단
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Currency = Literal["USD", "KRW", "JPY", "TWD", "CNY"]


class GroundedNumber(BaseModel):
    """출처 첨부가 강제된 수치 스칼라.

    LLM 출력에 강제: Gemini response_schema 로 사용해 환각 차단.
    """

    model_config = ConfigDict(extra="forbid")

    value: float = Field(description="실제 수치값")
    currency: Currency = Field(description="통화 코드 (ISO 4217)")
    citation_ids: list[UUID] = Field(
        min_length=1,
        description="이 수치를 뒷받침하는 citations 테이블 PK 1개 이상",
    )
    is_hypothesis: bool = Field(
        default=False,
        description="True 면 UI 에서 점선/회색 표시. is_imputed 와 함께 사용",
    )
    confidence: int = Field(
        default=80,
        ge=1,
        le=100,
        description="신뢰도 0-100. 50 미만이면 '추정치' 워터마크",
    )


class EdgeMetricOutput(BaseModel):
    """단일 엣지(공급-구매 관계)의 분기 정량화 결과.

    QuantEstimator (T2.5) 의 산출물. revenue 는 P × Q 또는 직접 수집값.
    """

    model_config = ConfigDict(extra="forbid")

    edge_id: UUID
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")
    price: GroundedNumber | None = None
    quantity: GroundedNumber | None = None
    revenue: GroundedNumber
    is_imputed: bool = Field(
        default=False,
        description="True 면 결측치를 시장점유율 등으로 역산. citation은 imputation 근거로",
    )


class CitationRecord(BaseModel):
    """validation.py 에서 사용하는 DB 조회 결과 표현.

    DB의 citations 테이블 부분 투영 (id + publish_date 만).
    """

    model_config = ConfigDict(extra="ignore")

    id: UUID
    publish_date: date
