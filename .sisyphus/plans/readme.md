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
