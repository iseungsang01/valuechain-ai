"""Run 영속화 서비스 (Phase 1 MVP - in-memory).

T3.1: POST /api/runs 가 호출되면 run_id 를 발급하고 메타데이터를 보관.
GET /api/runs/{id}/stream 가 run_id 로 조회 후 파이프라인 실행.

V2+ 확장: SupabaseRunStore 가 동일 RunStore Protocol 만족 → 점진 교체.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

RunStatus = Literal["pending", "running", "completed", "failed"]


@dataclass(frozen=True)
class RunRecord:
    """파이프라인 실행 메타데이터.

    DB schema (supabase migration 7. runs 테이블) 와 1:1 매핑.
    """

    run_id: str
    sector: str
    target_quarter: str
    is_backtest: bool
    as_of_date: datetime
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class RunStore(Protocol):
    """RunStore 인터페이스 - InMemory + Supabase 양쪽 구현용."""

    def create(
        self,
        *,
        sector: str,
        target_quarter: str,
        is_backtest: bool,
        as_of_date: datetime,
    ) -> RunRecord: ...

    def get(self, run_id: str) -> RunRecord | None: ...

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error_message: str | None = None,
    ) -> RunRecord | None: ...

    def list_recent(self, limit: int = 50) -> list[RunRecord]: ...


class InMemoryRunStore:
    """단일 프로세스 dict 기반 - Phase 1 MVP.

    RLock 으로 동시 접근 안전 (FastAPI async 환경에서 여러 SSE 동시 실행 가능).
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        sector: str,
        target_quarter: str,
        is_backtest: bool,
        as_of_date: datetime,
    ) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid4()),
            sector=sector,
            target_quarter=target_quarter,
            is_backtest=is_backtest,
            as_of_date=as_of_date,
            status="pending",
            started_at=datetime.now(UTC),
        )
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error_message: str | None = None,
    ) -> RunRecord | None:
        with self._lock:
            existing = self._runs.get(run_id)
            if existing is None:
                return None
            updated = replace(
                existing,
                status=status,
                completed_at=(
                    datetime.now(UTC)
                    if status in ("completed", "failed")
                    else existing.completed_at
                ),
                error_message=error_message,
            )
            self._runs[run_id] = updated
            return updated

    def list_recent(self, limit: int = 50) -> list[RunRecord]:
        with self._lock:
            sorted_runs = sorted(
                self._runs.values(), key=lambda r: r.started_at, reverse=True
            )
            return sorted_runs[:limit]


# ============================================================
# 싱글톤 - FastAPI dependency injection 진입점
# ============================================================

_default_store: RunStore = InMemoryRunStore()


def get_run_store() -> RunStore:
    """FastAPI Depends() 호환. 테스트 시 override 가능."""
    return _default_store
