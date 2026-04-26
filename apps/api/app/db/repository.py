"""DB Repository - Protocol + InMemory 구현 (Phase 1 MVP).

설계:
- Protocol 로 추상화 → DataCollector / QuantEstimator / Evaluator 모두 같은 인터페이스 사용
- InMemoryRepository = 단일 프로세스 dict 기반 (테스트/로컬)
- SupabaseRepository (V2+) = 동일 Protocol 만족하는 실제 DB 구현체

테이블 매핑:
- CompanyRecord     <-> public.companies
- EdgeRecord        <-> public.edges
- CitationRecord    <-> public.citations (이미 schemas/grounded.py 에 정의)
- EdgeMetricRecord  <-> public.edge_metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from app.schemas.grounded import CitationRecord
from app.sources.types import SourceCitation

Country = Literal["KR", "US", "JP", "TW", "CN"]


@dataclass(frozen=True)
class CompanyRecord:
    id: UUID
    ticker: str
    name: str
    country: Country
    sector: str


@dataclass(frozen=True)
class EdgeRecord:
    id: UUID
    supplier_id: UUID
    buyer_id: UUID
    product_category: str
    lag_quarters: int


@dataclass(frozen=True)
class EdgeMetricRecord:
    id: UUID
    edge_id: UUID
    quarter: str
    revenue: float | None
    price: float | None
    quantity: float | None
    currency: str
    is_imputed: bool
    is_hypothesis: bool
    confidence_score: int | None


# ============================================================
# Protocol
# ============================================================


class CompanyRepository(Protocol):
    """DataCollector / QuantEstimator / Evaluator 가 사용하는 단일 인터페이스."""

    # ---------- companies ----------
    def upsert_company(
        self, *, ticker: str, name: str, country: Country, sector: str
    ) -> CompanyRecord: ...

    def get_company_by_ticker(self, ticker: str) -> CompanyRecord | None: ...

    def list_companies(self) -> list[CompanyRecord]: ...

    # ---------- edges ----------
    def get_or_create_edge(
        self,
        *,
        supplier_id: UUID,
        buyer_id: UUID,
        product_category: str,
        lag_quarters: int,
    ) -> EdgeRecord: ...

    def list_edges(self) -> list[EdgeRecord]: ...

    # ---------- citations ----------
    def upsert_citation(self, citation: SourceCitation) -> CitationRecord: ...

    def get_citation(self, citation_id: UUID) -> CitationRecord | None: ...

    def lookup_citations(self, ids: list[UUID]) -> list[CitationRecord]: ...

    # ---------- edge_metrics ----------
    def upsert_edge_metric(
        self,
        *,
        edge_id: UUID,
        quarter: str,
        revenue: float | None,
        price: float | None = None,
        quantity: float | None = None,
        currency: str = "USD",
        is_imputed: bool = False,
        is_hypothesis: bool = False,
        confidence_score: int | None = None,
    ) -> EdgeMetricRecord: ...

    def link_metric_citation(
        self, *, metric_id: UUID, citation_id: UUID, weight: float = 1.0
    ) -> None: ...

    def list_edge_metrics(self, *, quarter: str | None = None) -> list[EdgeMetricRecord]: ...

    def get_metric_citations(self, metric_id: UUID) -> list[UUID]: ...


# ============================================================
# In-Memory implementation (Phase 1 MVP)
# ============================================================


@dataclass
class InMemoryRepository:
    """단일 프로세스 dict 기반 - 테스트/로컬 개발 용.

    프로덕션 SupabaseRepository 와 동일 Protocol 을 만족.
    """

    _companies_by_id: dict[UUID, CompanyRecord] = field(default_factory=dict)
    _companies_by_ticker: dict[str, CompanyRecord] = field(default_factory=dict)
    _edges_by_id: dict[UUID, EdgeRecord] = field(default_factory=dict)
    _edges_by_key: dict[tuple[UUID, UUID, str], EdgeRecord] = field(default_factory=dict)
    _citations_by_id: dict[UUID, CitationRecord] = field(default_factory=dict)
    _citations_by_disclosure: dict[tuple[str, str], CitationRecord] = field(
        default_factory=dict
    )
    _edge_metrics_by_id: dict[UUID, EdgeMetricRecord] = field(default_factory=dict)
    _edge_metrics_by_key: dict[tuple[UUID, str], EdgeMetricRecord] = field(
        default_factory=dict
    )
    _metric_citations: dict[UUID, list[tuple[UUID, float]]] = field(default_factory=dict)

    # ---------- companies ----------
    def upsert_company(
        self, *, ticker: str, name: str, country: Country, sector: str
    ) -> CompanyRecord:
        existing = self._companies_by_ticker.get(ticker)
        if existing:
            return existing
        rec = CompanyRecord(
            id=uuid4(), ticker=ticker, name=name, country=country, sector=sector
        )
        self._companies_by_id[rec.id] = rec
        self._companies_by_ticker[ticker] = rec
        return rec

    def get_company_by_ticker(self, ticker: str) -> CompanyRecord | None:
        return self._companies_by_ticker.get(ticker)

    def list_companies(self) -> list[CompanyRecord]:
        return list(self._companies_by_id.values())

    # ---------- edges ----------
    def get_or_create_edge(
        self,
        *,
        supplier_id: UUID,
        buyer_id: UUID,
        product_category: str,
        lag_quarters: int,
    ) -> EdgeRecord:
        if supplier_id == buyer_id:
            raise ValueError("self-loop edges forbidden")
        key = (supplier_id, buyer_id, product_category)
        existing = self._edges_by_key.get(key)
        if existing:
            return existing
        rec = EdgeRecord(
            id=uuid4(),
            supplier_id=supplier_id,
            buyer_id=buyer_id,
            product_category=product_category,
            lag_quarters=lag_quarters,
        )
        self._edges_by_id[rec.id] = rec
        self._edges_by_key[key] = rec
        return rec

    def list_edges(self) -> list[EdgeRecord]:
        return list(self._edges_by_id.values())

    # ---------- citations ----------
    def upsert_citation(self, citation: SourceCitation) -> CitationRecord:
        # DART/EDGAR 의 disclosure_id 가 unique key
        if citation.disclosure_id and citation.source_type in ("DART", "EDGAR"):
            dedupe_key = (citation.source_type, citation.disclosure_id)
            existing = self._citations_by_disclosure.get(dedupe_key)
            if existing:
                return existing
            rec = CitationRecord(id=uuid4(), publish_date=citation.publish_date)
            self._citations_by_id[rec.id] = rec
            self._citations_by_disclosure[dedupe_key] = rec
            return rec

        # disclosure_id 없는 citation 은 source_url 기반 dedupe
        for c in self._citations_by_id.values():
            if c.publish_date == citation.publish_date and str(citation.source_url) in (
                # url 는 비교 키로 사용; CitationRecord 가 id+publish_date 만 갖고 있어서
                # 보조 캐시 필요. Phase 1 MVP는 단순화로 매번 새로 생성.
                str(citation.source_url),
            ):
                pass
        rec = CitationRecord(id=uuid4(), publish_date=citation.publish_date)
        self._citations_by_id[rec.id] = rec
        return rec

    def get_citation(self, citation_id: UUID) -> CitationRecord | None:
        return self._citations_by_id.get(citation_id)

    def lookup_citations(self, ids: list[UUID]) -> list[CitationRecord]:
        return [c for cid in ids if (c := self._citations_by_id.get(cid))]

    # ---------- edge_metrics ----------
    def upsert_edge_metric(
        self,
        *,
        edge_id: UUID,
        quarter: str,
        revenue: float | None,
        price: float | None = None,
        quantity: float | None = None,
        currency: str = "USD",
        is_imputed: bool = False,
        is_hypothesis: bool = False,
        confidence_score: int | None = None,
    ) -> EdgeMetricRecord:
        key = (edge_id, quarter)
        existing = self._edge_metrics_by_key.get(key)
        if existing:
            # Phase 1 단순화: 마지막 쓰기가 이김
            self._edge_metrics_by_id.pop(existing.id, None)
        rec = EdgeMetricRecord(
            id=uuid4(),
            edge_id=edge_id,
            quarter=quarter,
            revenue=revenue,
            price=price,
            quantity=quantity,
            currency=currency,
            is_imputed=is_imputed,
            is_hypothesis=is_hypothesis,
            confidence_score=confidence_score,
        )
        self._edge_metrics_by_id[rec.id] = rec
        self._edge_metrics_by_key[key] = rec
        return rec

    def link_metric_citation(
        self, *, metric_id: UUID, citation_id: UUID, weight: float = 1.0
    ) -> None:
        if metric_id not in self._edge_metrics_by_id:
            raise KeyError(f"unknown metric_id {metric_id}")
        if citation_id not in self._citations_by_id:
            raise KeyError(f"unknown citation_id {citation_id}")
        self._metric_citations.setdefault(metric_id, []).append((citation_id, weight))

    def list_edge_metrics(self, *, quarter: str | None = None) -> list[EdgeMetricRecord]:
        records = list(self._edge_metrics_by_id.values())
        if quarter:
            records = [r for r in records if r.quarter == quarter]
        return records

    def get_metric_citations(self, metric_id: UUID) -> list[UUID]:
        return [cid for cid, _w in self._metric_citations.get(metric_id, [])]


# ============================================================
# 직렬화 헬퍼 - state 에 dict 형태로 보관할 때
# ============================================================


def serialize_company(rec: CompanyRecord) -> dict:
    return {
        "id": str(rec.id),
        "ticker": rec.ticker,
        "name": rec.name,
        "country": rec.country,
        "sector": rec.sector,
    }


def serialize_metric(rec: EdgeMetricRecord) -> dict:
    return {
        "id": str(rec.id),
        "edge_id": str(rec.edge_id),
        "quarter": rec.quarter,
        "revenue": rec.revenue,
        "price": rec.price,
        "quantity": rec.quantity,
        "currency": rec.currency,
        "is_imputed": rec.is_imputed,
        "is_hypothesis": rec.is_hypothesis,
        "confidence_score": rec.confidence_score,
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


def quarter_to_publish_floor(quarter: str) -> date:
    """분기 종료일 - 공시 publish_date 추정 fallback (실제 응답에서 모를 때)."""
    year = int(quarter[:4])
    q = int(quarter[-1])
    return {
        1: date(year, 3, 31),
        2: date(year, 6, 30),
        3: date(year, 9, 30),
        4: date(year, 12, 31),
    }[q]
