# ValueChain AI

> 공급망 기반 기업 재무 추정 및 예측 에이전트 (SaaS)

투자자, 애널리스트, 기관 리서처를 위한 AI 기반 공급망 정합성 검증 + 미래 수급 충돌 탐지 플랫폼.

https://glaze-frost-837.notion.site/ValueChain-AI-34e9306873568088a656c2a249889131?source=copy_link

## 핵심 가치

- **Network Consistency**: 공급망 전체에서 A의 매출 ≈ B의 매입 정합성 자동 검증
- **Forward Conflict Detection**: 전·후방 가이던스 모순으로 미래 수급 불균형(알파) 포착
- **Self-Optimization**: 백테스트로 추론 로직을 스스로 개선하는 자가 진화 시스템

## 아키텍처

```
[Next.js 16 Web] ←─SSE─→ [FastAPI Gateway] ←──→ [LangGraph 4 Agents]
                                  │                       │
                                  │              ┌────────┼────────┐
                                  │              ↓        ↓        ↓
                                  │         [DART API][EDGAR][FX/ECOS]
                                  ↓
                          [Supabase Postgres + pgvector]
```

자세한 설계: [.sisyphus/plans/valuechain-ai-architecture.md](./.sisyphus/plans/valuechain-ai-architecture.md)

## 모노레포 구조

```
.
├── apps/
│   ├── web/          # Next.js 16 + React 19 + Tailwind v4 + React Flow
│   └── api/          # FastAPI + LangGraph + Google Gemini (Python 3.11)
├── packages/
│   └── shared/       # 공통 TypeScript 타입 정의
├── .sisyphus/
│   └── plans/        # 설계 문서 (Momus 승인 v1.1)
└── package.json      # npm workspaces (root)
```

## 개발 환경 셋업

### 사전 요구사항

- Node.js 20+ (확인: `node --version`)
- npm 10+ (Node와 함께 설치됨)
- Python 3.11+ (확인: `python --version`)
- Git 2.x

### 설치

```bash
# 1. Repo 클론
git clone <this-repo>
cd contest2

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 실제 키 값 입력

# 3. 의존성 설치 (frontend)
npm install

# 4. Python 의존성은 apps/api에서 별도 (T1.3에서 셋업)
```

### 개발 서버 실행

```bash
# 프론트엔드 개발 서버
npm run dev:web

# 백엔드 (apps/api 셋업 후)
# T1.3 완료 시 추가 예정
```

## 진행 상황

Phase 1 MVP (4주) - 자세한 태스크는 [`.sisyphus/plans/valuechain-ai-architecture.md`](./.sisyphus/plans/valuechain-ai-architecture.md) §10 참조.

### Week 1 ✅ - 인프라 + 데이터 수집 골격

- [x] T1.1 Monorepo 구조 셋업
- [x] T1.2 Supabase 스키마 마이그레이션
- [x] T1.3 FastAPI 골격
- [x] T1.4 Next.js 16 + React Flow 골격
- [x] T1.5 DART OpenAPI 어댑터
- [x] T1.6 SEC EDGAR 어댑터
- [x] T1.7 FX rate 어댑터

### Week 2 ✅ - 멀티 에이전트 골격

- [x] T2.1 LangGraph 셋업 + PostgresSaver/MemorySaver + State 정의
- [x] T2.2 Structure Mapper 노드 + 메모리 반도체 토폴로지 (DB seed 동기화)
- [x] T2.3 Data Collector 노드 (DART/EDGAR + Time Isolation + InMemoryRepo)
- [x] T2.4 Pydantic GroundedNumber + 검증 미들웨어 (Mandatory Grounding)
- [x] T2.5 Quant Estimator 노드 (FX 환산 + 휴리스틱 매출 분배)
- [x] T2.6 Evaluator 노드 Reconciliation (inflow vs COGS 정합성)

**Week 2 합격 기준**: ✅ 4개 LangGraph 노드 end-to-end (96/96 tests pass)

### Week 3 ✅ - 스트리밍 + UI

- [x] T3.1 FastAPI SSE 엔드포인트 + LangGraph 스트림 변환 (`POST /api/runs` + `GET /api/runs/{id}/stream`)
- [x] T3.2 React Flow CompanyNode + TradeEdge 커스텀 컴포넌트
- [x] T3.3 SSE Hook (`useAgentStream`) + ThoughtPanel + CitationCard
- [x] T3.4 정합성 오차 시각화 (EdgeTooltip + ReconciliationLegend) + 출처 hover

**Week 3 합격 기준**: ✅ SSE 스트리밍 + 시각화 + 출처 표시 모두 작동 (110/110 backend tests pass, frontend build clean)

### Week 4 ✅ - 마무리 + 검증

- [x] T4.1 E2E 시나리오: 메모리 반도체 2024Q3 워크플로우 (Playwright Chromium + Firefox 18/18)
- [x] T4.2 에러 처리 + Fallback (분류된 에러 핸들러 + ErrorBoundary + AgentErrorPanel + SSE 자동 재연결 3회)
- [x] T4.3 데모 시드 데이터 + 성능 측정 (`scripts/seed_demo.py` + `scripts/benchmark.py`, TTFGraph p95 < 0.02s)
- [x] T4.4 데모 자료 + 회고 ([`docs/MVP_DEMO.md`](./docs/MVP_DEMO.md), [`docs/RETROSPECTIVE.md`](./docs/RETROSPECTIVE.md))

**Week 4 합격 기준**: ✅ TTFGraph SLA 충족 (p95 < 60s), 에러 처리 견고 (25 백엔드 + 6 E2E 테스트), 시연 가능 상태 (135/135 backend + 18/18 E2E pass)

## 라이선스

Private (TBD)
