# ValueChain AI - API (FastAPI Backend)

> Phase 1 MVP backend. FastAPI + LangGraph + Google Gemini.

## 로컬 개발

### 1. Python 가상환경

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate     # macOS/Linux

pip install --upgrade pip
pip install -e ".[dev]"          # pyproject.toml의 dev extras
```

### 2. 환경 변수

monorepo root의 `.env` 파일을 그대로 사용. `Settings`가 자동으로 `apps/api/.env` → `../../.env` 순으로 탐색.

### 3. 개발 서버

```powershell
cd apps/api
uvicorn main:app --reload --port 8000
```

확인:

```powershell
curl http://localhost:8000/api/health
# {"status":"ok","service":"valuechain-api","version":"0.1.0",...}

# OpenAPI Docs
# http://localhost:8000/docs
```

### 4. 테스트

```powershell
pytest -v
```

## 배포 (Railway)

```powershell
# 1. Railway 프로젝트 생성 (https://railway.com)
# 2. GitHub repo 연결, root directory = apps/api
# 3. 환경변수 설정 (Railway Dashboard):
#    - SUPABASE_URL
#    - SUPABASE_SERVICE_ROLE_KEY
#    - DATABASE_URL
#    - GEMINI_API_KEY
#    - DART_API_KEY
#    - SEC_USER_AGENT
#    - ECOS_API_KEY
#    - ENVIRONMENT=production
# 4. railway.json이 Dockerfile 빌드 + 헬스체크 자동 처리
```

## 구조

```
apps/api/
├── main.py                  # FastAPI app entry
├── pyproject.toml           # 의존성 + 도구 설정
├── requirements.txt         # Railway용 pinned
├── Dockerfile               # Railway 빌드용
├── railway.json             # Railway 설정
├── Procfile                 # 대안 (Render 등)
├── app/
│   ├── __init__.py
│   ├── config/              # Pydantic Settings
│   ├── routes/              # FastAPI 라우터 (/api/health)
│   ├── sources/             # 데이터 어댑터 (DART/EDGAR/ECOS) - W1
│   ├── agents/              # LangGraph 멀티 에이전트 - W2
│   │   ├── state.py         # PipelineState TypedDict + reducer
│   │   ├── graph.py         # 4-노드 StateGraph 컴파일러
│   │   ├── checkpointer.py  # MemorySaver / PostgresSaver 팩토리
│   │   ├── deps.py          # PipelineDeps - 노드 의존성 주입 컨테이너
│   │   ├── nodes/           # 4 에이전트 노드
│   │   │   ├── structure_mapper.py
│   │   │   ├── data_collector.py
│   │   │   ├── quant_estimator.py
│   │   │   └── evaluator.py
│   │   └── topology/        # 정적 섹터 토폴로지
│   │       └── memory_semi.py
│   ├── db/                  # Repository 추상화 (InMemory + Supabase) - W2
│   │   └── repository.py
│   ├── schemas/             # GroundedNumber + EdgeMetricOutput - W2
│   │   └── grounded.py
│   └── services/            # 비즈니스 로직
│       ├── validation.py    # Mandatory Grounding 검증 - W2
│       ├── imputation.py    # 매출 분배 휴리스틱 + FX - W2
│       └── reconciliation.py # 정합성 검증 (inflow vs COGS) - W2
└── tests/                   # 96 tests passing
    ├── test_health.py
    ├── test_sources.py      # W1: DART/EDGAR/ECOS adapters
    ├── test_graph.py        # W2: LangGraph state + checkpointer
    ├── test_structure_mapper.py
    ├── test_data_collector.py
    ├── test_grounded.py     # W2: GroundedNumber + validation
    ├── test_quant.py
    ├── test_reconciliation.py
    └── test_pipeline_e2e.py # W2: 4-node end-to-end
```
