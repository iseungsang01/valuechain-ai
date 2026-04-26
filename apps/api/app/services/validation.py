"""Mandatory Grounding - 사후 검증 (ADR-005 Layer 3) + Time Isolation (ADR-003 Layer 2).

검증 흐름:
1. citation_ids 가 비었는가?  → Pydantic 이 이미 차단 (min_length=1)
2. 모든 citation_ids 가 DB 에 존재하는가? → GroundingError (가공 UUID 차단)
3. 모든 citation 의 publish_date <= as_of_date 인가? → TimeIsolationError
   (백테스트 시 미래 데이터 누설 방지)

DB 의존성을 Callable 로 주입 → 테스트에서 mock 주입 용이, 결합도 ↓.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from uuid import UUID

from app.schemas.grounded import CitationRecord, GroundedNumber

# DB lookup 인터페이스 - 외부 주입 (Supabase client / SQLAlchemy / dict mock 등)
CitationLookup = Callable[[Sequence[UUID]], list[CitationRecord]]


class GroundingError(Exception):
    """citation_ids 중 일부가 DB 에 존재하지 않음 (LLM 환각 의심)."""

    def __init__(self, missing_ids: Sequence[UUID]) -> None:
        self.missing_ids = list(missing_ids)
        super().__init__(f"Fabricated citations not found in DB: {self.missing_ids}")


class TimeIsolationError(Exception):
    """백테스트 시점 이후의 citation 사용 시도 (미래 정보 누설)."""

    def __init__(
        self,
        offending: Sequence[CitationRecord],
        as_of_date: date,
    ) -> None:
        self.offending = list(offending)
        self.as_of_date = as_of_date
        msg = (
            f"Time isolation breach: {len(offending)} citations have "
            f"publish_date > as_of_date {as_of_date.isoformat()}: "
            f"{[(str(c.id), c.publish_date.isoformat()) for c in offending]}"
        )
        super().__init__(msg)


def validate_grounded_number(
    number: GroundedNumber,
    *,
    lookup: CitationLookup,
    as_of_date: date,
) -> None:
    """단일 GroundedNumber 의 grounding + time isolation 검증.

    Args:
        number: 검증 대상 수치.
        lookup: citation_ids -> CitationRecord 리스트로 변환하는 함수.
                DB 조회 또는 테스트 mock.
        as_of_date: 시점 격리 기준일 (백테스트 시 과거 시점, 라이브 시 today).

    Raises:
        GroundingError: 가공 citation_id 발견.
        TimeIsolationError: publish_date > as_of_date 인 citation 발견.
    """
    if not number.citation_ids:
        # Pydantic min_length=1 이 막아야 하지만 방어적 체크
        raise GroundingError(missing_ids=[])

    found = lookup(number.citation_ids)
    found_ids = {c.id for c in found}

    missing = [cid for cid in number.citation_ids if cid not in found_ids]
    if missing:
        raise GroundingError(missing_ids=missing)

    # 시점 격리 검증 (Layer 2)
    leaked = [c for c in found if c.publish_date > as_of_date]
    if leaked:
        raise TimeIsolationError(offending=leaked, as_of_date=as_of_date)


def validate_grounded_numbers(
    numbers: Sequence[GroundedNumber],
    *,
    lookup: CitationLookup,
    as_of_date: date,
) -> None:
    """배치 검증 - 단일 lookup 호출로 모든 citation 일괄 조회.

    한 번에 여러 GroundedNumber 검증 시 lookup N+1 회피.
    실패 시 첫 번째 에러를 raise.
    """
    all_ids: list[UUID] = []
    for n in numbers:
        all_ids.extend(n.citation_ids)
    if not all_ids:
        return

    # dedupe (순서 유지)
    seen: set[UUID] = set()
    unique_ids: list[UUID] = []
    for cid in all_ids:
        if cid not in seen:
            seen.add(cid)
            unique_ids.append(cid)

    found = lookup(unique_ids)
    found_by_id: dict[UUID, CitationRecord] = {c.id: c for c in found}

    for number in numbers:
        missing = [cid for cid in number.citation_ids if cid not in found_by_id]
        if missing:
            raise GroundingError(missing_ids=missing)
        leaked = [
            found_by_id[cid]
            for cid in number.citation_ids
            if found_by_id[cid].publish_date > as_of_date
        ]
        if leaked:
            raise TimeIsolationError(offending=leaked, as_of_date=as_of_date)
