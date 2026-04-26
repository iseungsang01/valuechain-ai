"""LangGraph checkpointer factory.

원칙:
- 테스트/로컬: MemorySaver (인프로세스 dict, 의존성 없음)
- 프로덕션 (DATABASE_URL 설정 시): AsyncPostgresSaver → Supabase Postgres에 영속화

PostgresSaver 는 첫 사용 전 .setup() 으로 langgraph_checkpoints 등 테이블 생성 필요.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver

from app.config.settings import get_settings

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def get_checkpointer(*, force_memory: bool = False) -> BaseCheckpointSaver:
    """기본 동기 checkpointer (테스트/단순 invoke 용).

    Phase 1 MVP는 MemorySaver만 사용한다. PostgresSaver 통합은 Phase 2+에서
    AsyncPostgresSaver 와 함께 별도 컨텍스트 매니저 패턴으로 도입.

    Args:
        force_memory: 호환성용 (현재는 항상 MemorySaver). V2에서 분기 추가.
    """
    settings = get_settings()
    # Phase 1: 단순화 - 항상 MemorySaver
    # V2 구현 메모: AsyncPostgresSaver.from_conn_string(...) 은 async context manager로
    # 외부에서 lifespan 관리 필요 → 현재 동기 시그니처와 충돌. 별도 async factory로 분리 예정.
    _ = settings, force_memory
    return MemorySaver()
