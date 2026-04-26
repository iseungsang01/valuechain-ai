"""정적 토폴로지 정의 - 섹터별 노드/엣지.

Phase 1: 메모리 반도체만 (Q4 결정). V2+ 에서 다른 섹터 추가.
DB seed (supabase/seed.sql) 와 1:1 일치.
"""

from app.agents.topology.memory_semi import MEMORY_SEMICONDUCTOR_TOPOLOGY, get_topology

__all__ = ["MEMORY_SEMICONDUCTOR_TOPOLOGY", "get_topology"]
