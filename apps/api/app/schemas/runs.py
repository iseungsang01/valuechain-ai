"""Run + StreamEvent Pydantic 스키마.

Frontend ↔ Backend wire format - packages/shared/src/agents.ts 와 정확히 동기화.

설계 (architecture.md §4 / T3.1):
- RunCreateRequest/RunCreated: POST /api/runs 입출력
- StreamEvent*: GET /api/runs/{id}/stream SSE 페이로드

원칙:
- snake_case JSON wire 유지 (TS 와 일치)
- Literal 타입으로 Sector/Quarter/AgentName/StreamEventType 강제
- payload 는 모든 이벤트에 선택적으로 첨부 (백엔드 raw passthrough)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# Domain literals (shared/src/graph.ts 와 동기)
# ============================================================

Sector = Literal[
    "memory_semiconductor",
    "display_oled",
    "battery_secondary",
    "auto_parts",
]

# 'YYYYQn' 형식. Pydantic regex 로 강제.
QUARTER_PATTERN = r"^\d{4}Q[1-4]$"

AgentName = Literal[
    "StructureMapper",
    "DataCollector",
    "QuantEstimator",
    "Evaluator",
]

StreamEventType = Literal[
    "agent_start",
    "thought",
    "tool_call",
    "tool_result",
    "graph_update",
    "agent_complete",
    "pipeline_complete",
    "error",
]


# ============================================================
# Run create / response
# ============================================================


class RunCreateRequest(BaseModel):
    """POST /api/runs 입력. shared/src/agents.ts RunCreateRequest 와 일치."""

    model_config = ConfigDict(extra="forbid")

    sector: Sector
    target_quarter: str = Field(pattern=QUARTER_PATTERN, examples=["2024Q3"])
    is_backtest: bool = False
    # 백테스트 시 시간격리 기준점. None 이면 서버에서 utcnow() 적용.
    as_of_date: datetime | None = None


class RunCreateResponse(BaseModel):
    """POST /api/runs 출력. shared/src/agents.ts RunCreateResponse 와 일치."""

    run_id: str
    stream_url: str = Field(description="SSE GET 엔드포인트 (상대 경로)")


# ============================================================
# StreamEvent wire format (shared/src/agents.ts 와 1:1)
# ============================================================


class StreamEventBase(BaseModel):
    """모든 SSE 이벤트의 공통 베이스."""

    model_config = ConfigDict(extra="allow")  # variant 별 추가 필드 허용

    event_id: str  # UUID v4 - 클라 dedup용
    run_id: str
    agent: AgentName
    type: StreamEventType
    timestamp: str  # ISO-8601 UTC
    payload: dict[str, Any] = Field(default_factory=dict)
