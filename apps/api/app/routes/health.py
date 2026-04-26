"""Health check endpoint - Railway/Vercel/모니터링용."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """헬스체크 응답 스키마."""

    status: str
    service: str
    version: str
    environment: str
    timestamp: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """서버 health check.

    Railway/모니터링에서 호출. 의존성(DB, LLM) 체크는 별도 엔드포인트로.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="valuechain-api",
        version=__version__,
        environment=settings.environment,
        timestamp=datetime.now(UTC).isoformat(),
    )
