# =====================================================================
# ValueChain AI - API Dockerfile (Railway / Render 호환)
# =====================================================================
# Multi-stage 불필요한 단순 이미지 (Phase 1).
# 빌드 시간 < 2분, 이미지 크기 < 200MB 목표.
# =====================================================================

FROM python:3.11-slim

# 시스템 의존성 (psycopg에 libpq-dev 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 캐시 효율을 위해 의존성을 먼저 복사
WORKDIR /app
COPY requirements.txt /app/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 복사
COPY . /app

# 비루트 사용자
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Railway는 PORT 환경변수 주입
ENV PORT=8000
EXPOSE ${PORT}

# Healthcheck (Docker)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/api/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
