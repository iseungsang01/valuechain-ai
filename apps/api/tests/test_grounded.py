"""T2.4 - GroundedNumber + Mandatory Grounding validation 검증.

3가지 차단 케이스:
1. Pydantic - citation_ids 빈 리스트 → ValidationError
2. validation.py - 가공 UUID → GroundingError
3. validation.py - publish_date > as_of_date → TimeIsolationError
"""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.grounded import (
    CitationRecord,
    EdgeMetricOutput,
    GroundedNumber,
)
from app.services.validation import (
    GroundingError,
    TimeIsolationError,
    validate_grounded_number,
    validate_grounded_numbers,
)

# ============================================================
# Pydantic Layer (Layer 1)
# ============================================================


def test_grounded_number_requires_at_least_one_citation() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        GroundedNumber(value=100.0, currency="USD", citation_ids=[])


def test_grounded_number_rejects_unknown_currency() -> None:
    with pytest.raises(ValidationError):
        GroundedNumber(value=1.0, currency="EUR", citation_ids=[uuid4()])  # type: ignore[arg-type]


def test_grounded_number_clamps_confidence_range() -> None:
    with pytest.raises(ValidationError):
        GroundedNumber(value=1.0, currency="USD", citation_ids=[uuid4()], confidence=0)
    with pytest.raises(ValidationError):
        GroundedNumber(value=1.0, currency="USD", citation_ids=[uuid4()], confidence=101)


def test_grounded_number_default_is_hypothesis_false() -> None:
    n = GroundedNumber(value=1.0, currency="USD", citation_ids=[uuid4()])
    assert n.is_hypothesis is False
    assert n.confidence == 80


def test_grounded_number_forbids_extra_fields() -> None:
    """LLM 이 임의 필드 추가 시 차단."""
    with pytest.raises(ValidationError):
        GroundedNumber(  # type: ignore[call-arg]
            value=1.0,
            currency="USD",
            citation_ids=[uuid4()],
            random_field="hallucinated",
        )


def test_edge_metric_output_revenue_required() -> None:
    """EdgeMetricOutput: revenue 만 필수, price/quantity 는 optional."""
    cid = uuid4()
    eid = uuid4()
    metric = EdgeMetricOutput(
        edge_id=eid,
        quarter="2024Q3",
        revenue=GroundedNumber(value=100.0, currency="USD", citation_ids=[cid]),
    )
    assert metric.price is None
    assert metric.quantity is None
    assert metric.revenue.value == 100.0


def test_edge_metric_output_quarter_format() -> None:
    """quarter 필드는 YYYYQ[1-4] 패턴 강제."""
    cid = uuid4()
    eid = uuid4()
    with pytest.raises(ValidationError):
        EdgeMetricOutput(
            edge_id=eid,
            quarter="2024-Q3",  # invalid
            revenue=GroundedNumber(value=1.0, currency="USD", citation_ids=[cid]),
        )


# ============================================================
# Validation Layer (Layer 3) - Grounding
# ============================================================


def _make_lookup(records: list[CitationRecord]):
    """주입 가능한 lookup (테스트 mock)."""

    def lookup(ids):
        id_set = set(ids)
        return [r for r in records if r.id in id_set]

    return lookup


def test_validate_passes_when_all_citations_exist_and_in_time() -> None:
    cid = uuid4()
    record = CitationRecord(id=cid, publish_date=date(2024, 6, 1))
    number = GroundedNumber(value=1.0, currency="USD", citation_ids=[cid])

    # 예외 없이 통과
    validate_grounded_number(
        number,
        lookup=_make_lookup([record]),
        as_of_date=date(2024, 12, 31),
    )


def test_validate_raises_grounding_error_for_fabricated_uuid() -> None:
    fabricated = uuid4()
    number = GroundedNumber(value=1.0, currency="USD", citation_ids=[fabricated])

    with pytest.raises(GroundingError) as exc_info:
        validate_grounded_number(
            number,
            lookup=_make_lookup([]),  # 빈 DB
            as_of_date=date(2024, 12, 31),
        )

    assert fabricated in exc_info.value.missing_ids


def test_validate_partial_grounding_error_lists_missing_ids() -> None:
    real_cid = uuid4()
    fake_cid = uuid4()
    record = CitationRecord(id=real_cid, publish_date=date(2024, 1, 1))
    number = GroundedNumber(
        value=1.0, currency="USD", citation_ids=[real_cid, fake_cid]
    )

    with pytest.raises(GroundingError) as exc_info:
        validate_grounded_number(
            number,
            lookup=_make_lookup([record]),
            as_of_date=date(2024, 12, 31),
        )

    assert exc_info.value.missing_ids == [fake_cid]


# ============================================================
# Validation Layer - Time Isolation
# ============================================================


def test_validate_raises_time_isolation_error_for_future_publish() -> None:
    cid = uuid4()
    # citation 이 2024-12-15 에 published, but as_of_date 가 2024-09-30
    record = CitationRecord(id=cid, publish_date=date(2024, 12, 15))
    number = GroundedNumber(value=1.0, currency="USD", citation_ids=[cid])

    with pytest.raises(TimeIsolationError) as exc_info:
        validate_grounded_number(
            number,
            lookup=_make_lookup([record]),
            as_of_date=date(2024, 9, 30),  # T-time
        )

    assert exc_info.value.as_of_date == date(2024, 9, 30)
    assert len(exc_info.value.offending) == 1
    assert exc_info.value.offending[0].id == cid


def test_validate_allows_publish_on_exact_as_of_date() -> None:
    """publish_date == as_of_date 는 허용 (<= 비교)."""
    cid = uuid4()
    record = CitationRecord(id=cid, publish_date=date(2024, 9, 30))
    number = GroundedNumber(value=1.0, currency="USD", citation_ids=[cid])

    validate_grounded_number(
        number,
        lookup=_make_lookup([record]),
        as_of_date=date(2024, 9, 30),
    )


# ============================================================
# Batch Validation
# ============================================================


def test_batch_validation_dedupes_lookup_calls() -> None:
    """같은 citation 을 공유하는 여러 number 는 lookup 1회로."""
    shared_cid = uuid4()
    record = CitationRecord(id=shared_cid, publish_date=date(2024, 1, 1))

    call_count = {"n": 0}

    def lookup(ids):
        call_count["n"] += 1
        return [record] if shared_cid in ids else []

    numbers = [
        GroundedNumber(value=1.0, currency="USD", citation_ids=[shared_cid]),
        GroundedNumber(value=2.0, currency="USD", citation_ids=[shared_cid]),
        GroundedNumber(value=3.0, currency="USD", citation_ids=[shared_cid]),
    ]

    validate_grounded_numbers(numbers, lookup=lookup, as_of_date=date(2024, 12, 31))
    assert call_count["n"] == 1


def test_batch_validation_raises_first_error() -> None:
    real = uuid4()
    fake = uuid4()
    real_record = CitationRecord(id=real, publish_date=date(2024, 1, 1))

    numbers = [
        GroundedNumber(value=1.0, currency="USD", citation_ids=[real]),
        GroundedNumber(value=2.0, currency="USD", citation_ids=[fake]),  # 불량
    ]

    with pytest.raises(GroundingError):
        validate_grounded_numbers(
            numbers, lookup=_make_lookup([real_record]), as_of_date=date(2024, 12, 31)
        )


def test_batch_validation_handles_empty_list() -> None:
    """numbers 가 비어있으면 no-op."""
    validate_grounded_numbers([], lookup=lambda _: [], as_of_date=date(2024, 1, 1))
