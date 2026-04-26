"""FastAPI application entry point.

ValueChain AI Backend.

로컬 실행:  uvicorn main:app --reload --port 8000
프로덕션:  uvicorn main:app --host 0.0.0.0 --port $PORT
Railway:    Procfile 또는 Dockerfile에서 위 명령 호출
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.middleware import register_exception_handlers
from app.routes import health, runs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 시작/종료 lifecycle."""
    settings = get_settings()
    logger.info(
        "valuechain.startup",
        version=__version__,
        environment=settings.environment,
    )
    yield
    logger.info("valuechain.shutdown")


def create_app() -> FastAPI:
    """FastAPI app factory.

    테스트 시 별도 인스턴스 생성 가능.
    """
    settings = get_settings()

    app = FastAPI(
        title="ValueChain AI API",
        description="공급망 기반 기업 재무 추정 및 예측 에이전트",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # CORS - 프론트엔드 (Vercel) ↔ API (Railway) 허용
    # - allow_origins: 정확히 일치하는 오리진 (production, localhost)
    # - allow_origin_regex: vercel preview/branch 배포 (*.vercel.app) 자동 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex_or_none,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # 라우터 등록 (모든 엔드포인트는 /api prefix)
    app.include_router(health.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")

    # 전역 예외 핸들러 (T4.2)
    register_exception_handlers(app)

    return app


app = create_app()
