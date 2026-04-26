"""DB 추상화 레이어.

Phase 1 전략:
- Protocol 로 인터페이스 정의 (CompanyRepository 등)
- InMemoryRepository 로 테스트/개발용 구현 (의존성 0)
- SupabaseRepository (V2): 실제 Supabase 연결 시 구현체 추가

V2+ 마이그레이션: 동일 Protocol 을 만족하는 구현체로 교체만 하면 됨.
"""

from app.db.repository import (
    CompanyRecord,
    CompanyRepository,
    EdgeMetricRecord,
    EdgeRecord,
    InMemoryRepository,
)

__all__ = [
    "CompanyRecord",
    "CompanyRepository",
    "EdgeMetricRecord",
    "EdgeRecord",
    "InMemoryRepository",
]
