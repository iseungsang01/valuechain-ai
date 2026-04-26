"""Runs API - POST /api/runs + GET /api/runs/{id}/stream.

T3.1: 프론트엔드가 "Run" 버튼 클릭 시 호출하는 두 엔드포인트.

POST /api/runs:
- 입력: RunCreateRequest (sector, target_quarter, ...)
- 출력: RunCreateResponse (run_id, stream_url)
- 동작: RunStore 에 메타데이터 등록, run_id 발급

GET /api/runs/{run_id}/stream:
- SSE EventSourceResponse 로 LangGraph astream 결과를 wire format 으로 push
- 클라이언트는 EventSource(stream_url) 또는 fetch-event-source 로 구독
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.agents.demo_fixtures import build_demo_deps
from app.schemas.runs import RunCreateRequest, RunCreateResponse
from app.services.runs import RunStore, get_run_store
from app.services.stream import stream_pipeline_events

router = APIRouter(tags=["runs"])


# ============================================================
# POST /api/runs
# ============================================================


@router.post(
    "/runs",
    response_model=RunCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="파이프라인 실행 요청 - run_id + SSE 스트림 URL 반환",
)
def create_run(
    payload: RunCreateRequest,
    store: Annotated[RunStore, Depends(get_run_store)],
) -> RunCreateResponse:
    """RunStore 에 새 run 등록 후 stream URL 반환.

    실제 LangGraph 실행은 GET /api/runs/{run_id}/stream 호출 시 시작.
    """
    as_of = payload.as_of_date or datetime.now(UTC)

    record = store.create(
        sector=payload.sector,
        target_quarter=payload.target_quarter,
        is_backtest=payload.is_backtest,
        as_of_date=as_of,
    )

    return RunCreateResponse(
        run_id=record.run_id,
        # 상대 경로 - 프론트가 base URL 결합
        stream_url=f"/api/runs/{record.run_id}/stream",
    )


# ============================================================
# GET /api/runs/{run_id}/stream
# ============================================================


@router.get(
    "/runs/{run_id}/stream",
    summary="SSE 스트림 - LangGraph 파이프라인 실시간 사고 + 그래프 업데이트",
    response_class=EventSourceResponse,
)
async def stream_run(
    run_id: str,
    store: Annotated[RunStore, Depends(get_run_store)],
) -> EventSourceResponse:
    """LangGraph 4-노드 파이프라인을 실행하며 SSE 로 push.

    응답 헤더:
    - Content-Type: text/event-stream
    - Cache-Control: no-cache
    - X-Accel-Buffering: no (Nginx/Cloud proxy 버퍼링 차단)
    """
    record = store.get(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run_id={run_id} not found",
        )

    # Phase 1 MVP: 데모 모드만 지원. V2: env 키 보유 시 real deps 분기.
    deps = build_demo_deps()

    return EventSourceResponse(
        stream_pipeline_events(run=record, deps=deps, store=store),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
