# ValueChain AI - 시스템 아키텍처 설계 (v1.0 - APPROVED)

> **상태**: v1.0 ✅ **Momus 승인 완료** (구현 착수 가능)
> **승인일**: 2026-04-26
> **승인 요지**: "highly detailed, practical, and ready for execution. atomic steps with specific file paths, code snippets, and highly executable QA scenarios"
> **목적**: 7단계 시계열 추론 파이프라인 + 자가 진화 멀티 에이전트 SaaS

## 변경 이력
- **v0.1**: 초기 도메인 지식 기반 초안
- **v0.2**: 사용자 7개 의사결정 반영, §9(무료 데이터 전략)/§10(Phase 1 분해) 신설 → Momus REJECT
- **v0.3**: §10을 22개 atomic 태스크로 재작성, 파일 경로/실행 단계/QA 시나리오 추가
- **v1.0**: Momus 재검증 [OKAY] - 구현 착수 가능
- **v1.1**: 환경 제약 반영
  - pnpm → **npm workspaces**로 변경 (Windows pnpm 글로벌 설치 권한 이슈, 기능적 동일)
  - 결과: 모든 `pnpm` 명령은 `npm` 으로 치환. workspace 명령은 `npm run --workspace=apps/web` 형식
- **v1.2**: Python 환경 도구 결정
  - uv 미설치 → **표준 venv + pip + pyproject.toml** 사용 (PEP 621)
  - Railway 배포는 `requirements.txt` 사용 (자동 인식)
  - 개발 시: `pip install -e ".[dev]"` (pyproject.toml dev extras)
- **v1.3**: T1.4 구현 시 발견 사항
  - Next.js 16.2.4 명시했으나 React 19 + npm peer dep 해결로 **Next.js 15.5.15** 설치됨
  - 모든 요구 기능 지원 (App Router, Turbopack, Server Components, React 19)
  - 16 업그레이드는 V1+에서 (typedRoutes API 변경 등 마이너 차이)

---

---

## 0-Prime. 사용자 의사결정 (Locked-in)

| # | 결정 사항 | 영향 |
|---|---|---|
| Q1 | **Phase 1 단일 사용자**, V2(Phase 3)부터 Multi-tenant RLS | Auth/RLS 구현을 V2로 미룸. MVP 단순화 |
| Q2 | **유료 API 미사용** (무료 + 자체 수집만) | Tier 2 가이던스 수집 전략 재설계 필요 (§9 신설) |
| Q3 | **한국어 UI only** (i18n V2로 미룸) | next-intl 불필요. 메시지 한국어 하드코드 가능 |
| Q4 | **MVP 섹터 = 메모리 반도체** | 삼성/SK하이닉스/마이크론/인텔/엔비디아/AMD/TSMC 등 노드 풍부, DART+EDGAR 모두 활용 |
| Q5 | **Vercel(프론트) + Railway/Render(FastAPI)** | SSE 장시간 연결 안정. Supabase는 DB+Auth로만 사용 |
| Q6 | **백테스트 범위 12분기 (3년)** | 2022~2024 메모리 다운사이클/업사이클 1회전 포함. **매크로 충격 처리 필수** |
| Q7 | **MVP 성공 = 정합성 검증 1건 + 출처있는 그래프** | Forward Conflict/백테스트는 V1+로 미룸. 4주 안에 달성 가능 |



---

## 0. Executive Summary

**제품 정체성**: 단순 재무 조회 SaaS가 아닌 "공급망 정합성 검증기 + 미래 수급 충돌 탐지기"

**알파의 원천 (Why this matters)**:
- 일반 데이터 벤더는 "A사 매출 100억" 같은 점(node) 정보만 제공
- ValueChain AI는 "A→B→C 공급망 전체에서 시차 보정 후 매출/매입이 정합한가?" 검증
- "A는 +20% 증산, C는 -10% 수요 가이던스" 같은 **미래 모순(Forward Conflict)** 신호 추출
- 이는 기관 투자자가 컨센서스보다 빨리 포지션을 잡을 수 있는 **선행 알파**

**핵심 엔지니어링 챌린지** (어려움 순):
1. **시점 격리 (Time Isolation)** - 백테스팅 시 미래 정보 누설 0% 보장
2. **자가 진화 프롬프트** - Evaluator가 Quant의 프롬프트를 안전하게 수정
3. **Mandatory Grounding 강제** - 모든 수치에 출처 첨부, 환각 차단
4. **시계열 그래프 시각화 성능** - T-4~T+4 슬라이더 스크럽 시 100+ 노드 부드럽게 보간
5. **멀티 소스 정합성** - DART/EDGAR/관세청/뉴스 간 충돌 시 Tier 우선순위 자동 적용

---

## 1. 핵심 아키텍처 결정 (Architecture Decision Records)

### ADR-001: 멀티 에이전트 오케스트레이터 = **LangGraph**

**대안**: CrewAI, AutoGen, OpenAI Swarm, Custom

**선택**: **LangGraph** (Python)

**이유**:
- **Stateful 그래프 + 체크포인트**: 7단계 파이프라인을 노드/엣지로 명시적 모델링 가능. 단계별 state 영속화로 백테스트 재현성 확보.
- **시간 여행(Time Travel) 빌트인**: LangGraph의 `checkpointer`로 특정 스냅샷에서 재개/분기 가능 → 백테스트 모드의 "T-4 시점에서 다시 실행" 패턴과 정확히 부합.
- **스트리밍 1급 지원**: `astream_events()`로 토큰/노드/툴 이벤트를 SSE로 직접 파이프 가능.
- **Subgraph 컴포지션**: Evaluator가 Backtest 모드에서 전체 파이프라인을 Subgraph로 호출하는 패턴이 자연스러움.
- **자가 수정 프롬프트**: 노드의 system prompt를 state에서 읽도록 설계하면, Evaluator가 state의 prompt 필드를 mutate하는 것으로 자가 진화 구현.

**거부 이유**:
- CrewAI: 역할 기반 추상화는 좋으나, 시간 여행/체크포인트가 약함. 7단계 파이프라인의 결정성 부족.
- AutoGen: 대화형 에이전트에 강점, 결정적 파이프라인엔 과한 추상화.
- Custom: 6개월 이상의 인프라 작업이 필요. ROI 안 나옴.

**리스크**:
- LangGraph 프롬프트 mutation 시 state 직렬화 호환성 → 마이그레이션 스크립트 필요
- 코드 실행 (Quant 에이전트의 Python 연산) 샌드박스는 별도 통합 (E2B, Modal, Daytona 등)

---

### ADR-002: 데이터 저장소 = **Supabase (Postgres + pgvector + RLS)** + **TimescaleDB 익스텐션 검토**

**대안**: PostgreSQL + Neo4j + Pinecone, Pure PostgreSQL, MongoDB + Neo4j

**선택**: **Supabase Postgres** 단일 백엔드 (그래프/벡터/시계열/관계 모두 수용)

**이유**:
- **사용자 환경에 supabase 스킬이 설치되어 있음** → 우선 활용
- **Multi-tenant RLS**: SaaS 사용자별 워크스페이스 격리에 RLS가 강력
- **pgvector**: 출처 인용문 임베딩 (citation similarity search) 직접 지원
- **그래프 표현**: 노드/엣지 테이블 + 재귀 CTE로 supply chain depth 3까지 충분히 표현 (Neo4j 불필요)
- **TimescaleDB hypertable**: 분기별 시계열 데이터 (P, Q, FX rate) 자동 파티셔닝 → 대용량 백테스트 쿼리 빠름
- **Realtime**: Supabase Realtime으로 그래프 상태 변경을 프론트엔드에 push 가능 (SSE 보조 채널)

**스키마 핵심 테이블** (초안):
```sql
-- 기업 노드
companies (id, ticker, name, sector, country, ...)

-- 공급망 엣지 (방향성)
edges (id, supplier_id, buyer_id, product_category, lag_quarters, created_at)

-- 시계열 거래 데이터 (각 분기별 P, Q, Revenue)
edge_metrics (edge_id, quarter, price, quantity, revenue, currency,
              is_imputed, confidence_score, created_at)
-- ↑ TimescaleDB hypertable로 (quarter, edge_id) 기준 파티셔닝

-- 출처 인용 (Mandatory Grounding 핵심)
citations (id, source_url, source_type, source_tier, publish_date,
           disclosure_id, snippet, embedding vector(1536))

-- 메트릭-인용 다대다
metric_citations (metric_id, citation_id, weight)

-- 가이던스 (Forward Indicators)
guidance_records (company_id, metric_type, value, time_horizon,
                  source_citation_id, published_at, as_of_date)

-- 충돌 플래그
forward_conflicts (id, edge_id, supplier_guidance_id, buyer_guidance_id,
                   gap_pct, severity, detected_at)

-- 프롬프트 버전 (자가 진화 히스토리)
agent_prompts (id, agent_name, version, sector, prompt_text,
               parent_version_id, mutation_reason, mape_score, created_at)

-- 백테스트 결과
backtests (id, target_quarter, sector, predicted_value, actual_value,
           mape, prompt_version_id, executed_at)
```

**거부 이유**:
- Neo4j: 깊이 3 이하 + 분기별 시계열엔 과잉. 운영 부담 > 그래프 쿼리 이득.
- Pinecone/Weaviate: pgvector로 충분. 별도 시스템 비용/복잡성 증가.

**리스크**:
- 노드 수 1000+ / 엣지 수 5000+ 시 재귀 CTE 성능 한계 → 그때 Neo4j 도입 검토 (Phase 3+)

---

### ADR-003: 시점 격리 (Time Isolation) = **as_of_date 필수 인자 + DB 레벨 enforcement**

**가장 어려운 문제**: 백테스트 T-4 시점 시뮬레이션 시 T-3, T-2, T-1, T-0 데이터를 절대 보면 안 됨.

**3중 방어 체계**:

**Layer 1: 데이터 모델 레벨**
- 모든 데이터 행에 `created_at`, `published_at`, `effective_quarter` 3개 컬럼 강제
- `published_at` = 원천이 세상에 공개된 날짜 (예: 공시일, 기사 발행일)
- `effective_quarter` = 데이터가 가리키는 분기 (예: 2024Q3 매출)
- 둘은 다름 - 2024Q3 매출은 보통 2024-11에 published

**Layer 2: 쿼리 강제**
- 모든 데이터 접근 함수에 `as_of_date: datetime` 인자 필수
- Pydantic 모델에 `Annotated[datetime, "Required for time isolation"]`
- DB 뷰로 자동 필터: `CREATE VIEW citations_at_t AS SELECT * FROM citations WHERE published_at <= :as_of_date`
- 백테스트 모드에선 raw 테이블 접근 차단, 뷰만 노출

**Layer 3: LLM 컨텍스트 차단**
- 에이전트 시스템 프롬프트에 현재 모드 명시: "당신은 현재 {as_of_date} 시점에 위치합니다. 그 이후의 어떤 정보도 알지 못합니다."
- 도구 호출 결과를 검증하는 미들웨어가 `published_at > as_of_date`인 행이 있으면 즉시 throw

**Layer 4 (보조): 학습 데이터 컷오프 인지**
- Gemini의 학습 데이터 컷오프(예: 2024-04)는 이론적 누설 가능. 백테스트 분기를 LLM 컷오프 이후로 잡는 것을 권장
- 단, 이 누설은 미미하므로 v1에선 허용, v2에서 평가

**거부 패턴**:
- ❌ "정직한" 에이전트 가정 (프롬프트에만 의존)
- ❌ 별도 시간별 DB 스냅샷 (운영 비용 폭발)

---

### ADR-004: 자가 진화 프롬프트 = **Constrained Mutation + Human-in-the-Loop (초기) → 자율 (성숙기)**

**핵심 원칙**: 프롬프트는 "코드"이며, 그 변경은 코드 변경처럼 다뤄야 함.

**4단계 안전 장치**:

**Stage 1: 변경 제안 (Mutation Proposal)**
- Evaluator는 직접 프롬프트를 쓰지 않고, **JSON 형식의 "변경 제안서"** 생성:
```json
{
  "target_agent": "QuantEstimator",
  "sector": "memory_semiconductor",
  "trigger": "MAPE_15_3pct_in_downcycle_2023Q3",
  "proposed_rule": {
    "id": "downcycle-p-penalty",
    "condition": "is_downcycle == true",
    "modifier": "guidance_P *= 0.88",
    "rationale": "Backtest 5건에서 다운사이클 시 가이던스 P 평균 12% 과대추정 확인"
  },
  "evidence_backtest_ids": [123, 145, 167, 189, 201]
}
```

**Stage 2: 검증 (Sandbox A/B Test)**
- 새 규칙을 적용한 프롬프트 v2를 별도 분기에 만들어, 동일 백테스트 셋(5+ 건)에 재실행
- v1 대비 MAPE 개선 ≥ 5%p AND 다른 섹터에서 회귀 없음 → 통과

**Stage 3: 승인 (초기 = 사람, 성숙기 = 자동)**
- v0~v1: 사람 승인 후 적용 (PR 리뷰 형태)
- v2+: A/B 결과가 통과하면 자동 적용, 단 daily 변경 횟수 제한

**Stage 4: 롤백 (Drift Detection)**
- 적용 후 7일간 라이브 MAPE 추적
- 라이브 MAPE > 백테스트 MAPE + 10%p 면 자동 롤백

**프롬프트 버전 그래프**:
- `agent_prompts` 테이블이 DAG (parent_version_id) 형성
- 각 버전에 sector 태그 → 섹터별 프롬프트 분기 가능

---

### ADR-005: Mandatory Grounding 강제 = **Pydantic Schema + LLM Tool Forcing + Post-validation**

**3중 방어**:

**Layer 1: 출력 스키마 강제**
```python
class GroundedNumber(BaseModel):
    value: float
    currency: Literal["USD", "KRW", "JPY", ...]
    citation_ids: list[UUID] = Field(min_length=1)  # 1개 이상 필수
    is_hypothesis: bool = False
    confidence: int = Field(ge=1, le=100)

class EdgeMetricOutput(BaseModel):
    price: GroundedNumber
    quantity: GroundedNumber
    revenue: GroundedNumber
    # ...
```
- Gemini의 `response_schema` 기능 활용 → 스키마 위반 시 LLM이 재생성

**Layer 2: 도구 호출 강제**
- 에이전트가 출처를 만들려면 `lookup_citation(query, as_of_date)` 도구를 반드시 호출
- 도구 결과의 citation_id만 출력에 사용 가능 (sandbox)
- LLM이 가공의 citation_id를 만들어내면 후속 검증 단계에서 차단

**Layer 3: 사후 검증**
```python
def validate_grounded_output(output: EdgeMetricOutput, db: Session):
    for citation_id in output.price.citation_ids:
        if not db.query(Citation).get(citation_id):
            raise GroundingError(f"Fabricated citation: {citation_id}")
    # 인용 발행일이 as_of_date 이후면 시간격리 위반
    # ...
```

**환각 방지 추가 장치**:
- `is_hypothesis: true` 플래그가 붙은 데이터는 UI에서 점선/회색으로 명시
- 신뢰도 점수가 50 미만인 데이터는 "추정치" 워터마크

---

### ADR-006: Forward Conflict 탐지 알고리즘

**문제**: "A는 +20% 증산, B는 -10% 수요" 같은 모순을 정량화.

**알고리즘 (단순 → 정교 단계적 발전)**:

**v1 (Phase 2)**: 단순 비교
```python
def detect_conflict(edge: Edge, quarter: Quarter) -> Optional[ConflictFlag]:
    supplier_guidance = get_guidance(edge.supplier_id, "production_change_pct", quarter)
    buyer_guidance = get_guidance(edge.buyer_id, "demand_change_pct", quarter)

    if not (supplier_guidance and buyer_guidance):
        return None

    gap = abs(supplier_guidance.value - buyer_guidance.value)
    if gap > 10:  # 10%p 이상 차이
        return ConflictFlag(
            edge_id=edge.id,
            severity=min(gap / 5, 100),  # 5%p당 1점
            type="oversupply" if supplier_guidance.value > buyer_guidance.value else "shortage",
        )
```

**v2 (Phase 3)**: 다차원 정렬
- 가이던스 단위 정규화 (수량/매출/% 변환 표준)
- 시간 지평 정렬 (분기/연간 변환)
- 제품 카테고리 매칭 (한 엣지 내 여러 제품군 분리)
- 신뢰도 가중 (Tier 1 가이던스 vs Tier 3)

**v3 (Phase 4)**: ML 기반 false-positive 감소
- 과거 충돌 신호 → 실제 발생 여부 학습
- 섹터별 일반적 가이던스 vs 미래 가이던스 분리

**알파 가치 측정**: 충돌 감지 후 N분기 후 실적과 비교한 적중률을 backtests 테이블에 누적 → 사용자에게 "본 시그널의 과거 적중률 67%" 표시.

---

### ADR-007: 프론트엔드 상태 관리 = **Zustand + React Flow 내장 store + TanStack Query**

**역할 분리**:
- **TanStack Query**: 서버 상태 (그래프 데이터, 회사 정보) 캐싱/리페칭
- **Zustand**: UI 상태 (선택된 시점 t, 선택된 노드, 필터, 충돌 표시 토글)
- **React Flow 내장 store**: 노드/엣지 위치, 줌/팬 (라이브러리 자체 관리)
- **SSE EventSource (in custom hook)**: 에이전트 사고 스트림 실시간 표시

**시간 슬라이더 → 그래프 변환 패턴**:
```typescript
// Zustand store
const useTimeStore = create<TimeStore>((set) => ({
  currentQuarter: "2024Q3",
  setQuarter: (q) => set({ currentQuarter: q }),
}));

// 컴포넌트
const { currentQuarter } = useTimeStore();
const { data: graph } = useQuery({
  queryKey: ["graph", sectorId, currentQuarter],
  queryFn: () => fetchGraph(sectorId, currentQuarter),
  // 인접 분기 prefetch로 슬라이더 스크럽 부드럽게
});

// 노드/엣지 보간 (Framer Motion)
<AnimatePresence>
  <motion.div
    animate={{ width: nodeSize(graph.nodes[id].revenue) }}
    transition={{ duration: 0.3 }}
  />
</AnimatePresence>
```

**SSE vs WebSocket 결정**:
- SSE 1개 채널로 단방향 (서버 → 클라) 충분: 에이전트 사고 + 그래프 업데이트 모두
- 양방향 명령(에이전트 cancel)은 별도 REST `POST /api/runs/:id/cancel` 호출
- 이 분리가 단일 WebSocket보다 디버그/관찰 용이

**충돌 엣지 깜빡임**:
- React Flow custom edge 컴포넌트 + CSS animation (`@keyframes blink`)
- Tailwind v4의 `@property` + `animation-composition` 활용

---

## 2. 백엔드 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│  Next.js 16 App (Frontend)                               │
│  - SSE Hook (agent thoughts + graph updates)             │
│  - React Flow + Zustand                                  │
│  - Time Slider (T-4 ~ T+4)                               │
└────────────────┬─────────────────────────────────────────┘
                 │ SSE / REST
                 ↓
┌──────────────────────────────────────────────────────────┐
│  FastAPI Gateway (Python 3.12)                           │
│  - SSE-Starlette streaming                               │
│  - JWT auth (Supabase Auth)                              │
│  - Rate limiting                                         │
└────────────────┬─────────────────────────────────────────┘
                 │
       ┌─────────┴─────────┐
       ↓                   ↓
┌─────────────┐    ┌──────────────────┐
│ LangGraph   │    │  Background      │
│ Orchestrator│    │  Workers (Celery)│
│             │    │  - Backtest jobs │
│ ┌─────────┐ │    │  - Data ingest   │
│ │ Mapper  │ │    └──────────────────┘
│ ├─────────┤ │              ↓
│ │Collector│ │    ┌──────────────────┐
│ ├─────────┤ │    │  Tool Calls       │
│ │  Quant  │─┼───→│  - DART API      │
│ ├─────────┤ │    │  - EDGAR API     │
│ │Evaluator│ │    │  - Customs API   │
│ └─────────┘ │    │  - Earnings call │
└──────┬──────┘    │  - FX rate API   │
       │           │  - Code Sandbox  │
       ↓           │    (Modal/E2B)   │
┌──────────────┐   └──────────────────┘
│  Supabase    │
│  - Postgres  │
│  - pgvector  │
│  - Realtime  │
│  - Auth      │
│  - Storage   │
└──────────────┘
```

**핵심 모듈**:
- `apps/api/`: FastAPI app
  - `routes/`: REST + SSE 엔드포인트
  - `agents/`: LangGraph 그래프 정의 (4 에이전트 + 7단계 노드)
  - `tools/`: 데이터 소스 어댑터 (DART, EDGAR, FX, ...)
  - `schemas/`: Pydantic 모델 (GroundedNumber 등)
  - `services/`: 비즈니스 로직 (backtest runner, conflict detector)
  - `db/`: SQLAlchemy + Supabase 연결
- `apps/worker/`: Celery 워커 (백테스트 비동기 실행)
- `packages/shared-types/`: TypeScript ↔ Python 공유 스키마 (codegen)

---

## 3. 프론트엔드 아키텍처

```
apps/web/
├── app/                          # Next.js 16 App Router
│   ├── (marketing)/              # 랜딩
│   ├── dashboard/
│   │   ├── [sectorId]/
│   │   │   ├── page.tsx          # 메인 그래프 화면
│   │   │   ├── runs/[runId]/     # 실시간 에이전트 사고 패널
│   │   │   └── backtests/        # 백테스트 결과 비교
│   │   └── layout.tsx
│   └── api/                      # BFF (Supabase 직결 + SSE 프록시)
│
├── components/
│   ├── graph/
│   │   ├── SupplyChainFlow.tsx   # React Flow 컨테이너
│   │   ├── CompanyNode.tsx       # 매출=크기, 신뢰도=색상
│   │   ├── TradeEdge.tsx         # 물량=두께, 충돌=깜빡임
│   │   └── TimeSlider.tsx        # T-4 ~ T+4
│   ├── agent-stream/
│   │   ├── ThoughtPanel.tsx      # SSE 사고 스트림
│   │   └── CitationCard.tsx      # 출처 카드
│   ├── conflict/
│   │   └── ConflictTooltip.tsx
│   └── ui/                       # Tailwind v4 + Framer Motion 기반
│
├── hooks/
│   ├── useAgentStream.ts         # SSE EventSource 래퍼
│   ├── useGraphData.ts           # TanStack Query
│   └── useTimeNavigation.ts      # Zustand store
│
├── lib/
│   ├── supabase.ts               # Supabase 클라이언트
│   └── sse-client.ts             # microsoft/fetch-event-source 기반
│
└── stores/
    ├── timeStore.ts              # Zustand
    ├── filterStore.ts
    └── selectionStore.ts
```

---

## 4. 7단계 파이프라인 → LangGraph 노드 매핑

```python
from langgraph.graph import StateGraph
from typing import TypedDict, Optional

class PipelineState(TypedDict):
    sector: str
    target_quarter: str
    as_of_date: datetime  # 시간 격리 핵심
    is_backtest: bool
    topology: Optional[dict]
    raw_data: Optional[dict]
    quantified: Optional[dict]
    reconciliation_errors: list
    forward_conflicts: list
    confidence_map: dict
    backtest_metrics: Optional[dict]
    prompt_mutations: list  # Evaluator가 채움

graph = StateGraph(PipelineState)

# 7단계 노드 (각각 LangGraph 노드)
graph.add_node("structure_mapping", structure_mapper_node)        # Step 1
graph.add_node("data_harvesting", data_collector_node)            # Step 2
graph.add_node("quantification", quant_estimator_node)            # Step 3
graph.add_node("reconciliation", evaluator_reconcile_node)        # Step 4
graph.add_node("conflict_detection", evaluator_conflict_node)     # Step 5
graph.add_node("confidence_scoring", evaluator_confidence_node)   # Step 6
graph.add_node("backtest_self_refine", evaluator_refine_node)     # Step 7 (백테스트 모드만)

# 엣지: 순차 + 조건부
graph.add_edge("structure_mapping", "data_harvesting")
graph.add_edge("data_harvesting", "quantification")
graph.add_edge("quantification", "reconciliation")
graph.add_conditional_edges(
    "reconciliation",
    lambda s: "conflict_detection" if not s["reconciliation_errors"] else "quantification",
    # 정합성 실패 시 다시 정량화 (최대 3회)
)
graph.add_edge("conflict_detection", "confidence_scoring")
graph.add_conditional_edges(
    "confidence_scoring",
    lambda s: "backtest_self_refine" if s["is_backtest"] else END,
)

# 체크포인터 (시간 여행)
checkpointer = PostgresSaver(supabase_conn)
compiled = graph.compile(checkpointer=checkpointer)
```

---

## 5. Phasing Plan (MVP → V1 → V2)

### Phase 1 (MVP, 4주) — "정합성만 보인다"
- ✅ 단일 섹터 (예: 메모리 반도체) 하드코딩 토폴로지
- ✅ Tier 1 데이터만 (DART/EDGAR 공시 매출/COGS)
- ✅ 4개 에이전트 골격 (LangGraph)
- ✅ React Flow 정적 그래프 (시간 슬라이더 X, 단일 분기)
- ✅ 정합성 검증만 (Step 1-4)
- ✅ Mandatory Grounding 1차 (출처 카드 표시)
- ❌ 백테스트, 미래 투영, 자가 진화 없음
- **목표**: 사용자가 "이 시스템이 실제로 정합성을 본다"는 가치를 1번이라도 체험

### Phase 2 (V1, +6주) — "미래도 본다"
- ✅ 시간 슬라이더 (T-4 ~ T+4)
- ✅ Tier 2 가이던스 수집 (어닝스 콜)
- ✅ Quant의 미래 투영 (CAPEX/Backlog/Guidance)
- ✅ Forward Conflict 감지 v1 (단순 비교)
- ✅ 다중 섹터 (사용자가 선택)
- ✅ SSE 에이전트 사고 스트림
- **목표**: 알파 시그널이 처음으로 발생, 1건이라도 적중하면 PoC 성공

### Phase 3 (V2, +8주) — "스스로 진화한다"
- ✅ 백테스트 인프라 (시간 격리 3중 방어)
- ✅ Evaluator의 자가 진화 프롬프트 (Stage 1-3, Human-in-loop)
- ✅ 충돌 알고리즘 v2 (다차원 정렬)
- ✅ 신뢰도 점수 노출
- ✅ Multi-tenant Auth (Supabase Auth + RLS)
- **목표**: 시스템이 한 번이라도 자기 프롬프트를 개선했음을 증명

### Phase 4 (V3, +12주) — "신뢰할 수 있다"
- ✅ 자가 진화 자동 적용 (Stage 4 롤백 + 자율 승인)
- ✅ 충돌 알고리즘 ML 기반 v3
- ✅ 사용자별 워크스페이스, 리포트 export
- ✅ 알파 적중률 트래킹 (마케팅 자료화)

---

## 6. 리스크 레지스터 (Top 5)

| # | 리스크 | 가능성 | 영향 | 완화 |
|---|---|---|---|---|
| 1 | 시점 격리 누설 (백테스트가 미래를 본다) | 중 | 치명 | 3중 방어 + CI 테스트로 누설 검출 |
| 2 | 자가 진화 프롬프트 회귀 | 중 | 높음 | A/B + 자동 롤백 + 일일 mutation 한도 |
| 3 | 데이터 출처 API 변경/제한 | 높음 | 중 | 어댑터 패턴 + 폴백 소스 + 캐싱 |
| 4 | LLM 환각으로 가공 인용 | 중 | 높음 | Pydantic + 도구 강제 + 사후 검증 |
| 5 | 시각화 성능 (200+ 노드) | 중 | 중 | virtualization + 노드 클러스터링 |

---

## 7. ~~미해결 질문~~ → 의사결정 완료 (§0-Prime 참고)

7개 질문 모두 사용자 답변 수신 완료. §0-Prime 표 참고. 결정의 영향은 각 ADR에 반영됨.

---

## 8. 의사결정에 따른 ADR 보정 (v0.2)

### ADR-002 보정: Supabase 단일 백엔드 (확정)
- 사용자 환경에 supabase 스킬 설치 → 우선 활용 결정
- Phase 1: Auth/RLS 미사용 (단일 사용자). DB 스키마는 처음부터 `workspace_id` 컬럼 보유 (V2 마이그레이션 비용 0)
- TimescaleDB는 Phase 2(시계열 슬라이더 도입 시) 검토. Phase 1엔 일반 Postgres로 충분

### ADR-005 보정: Mandatory Grounding 강화
- Q2 결정으로 데이터 소스가 한정되므로(공시 중심), citation 검증이 더 중요
- Tier 1 (DART 공시) 출처는 disclosure_id로 unique 식별 가능 → DB unique constraint
- Tier 2/3는 URL + publish_date hash로 중복 차단

### ADR-007 보정: i18n 미사용
- 한국어 하드코드 (Phase 1)
- 단, **데이터/숫자 포매팅은 처음부터 라이브러리화** (`@/lib/format` 모듈) → V2 i18n 도입 시 호환

### Phase 매핑 보정
- Phase 1 (4주): **정합성 검증 1건 + 출처있는 그래프 = MVP 합격선**
  - Auth 없음, 단일 사용자, 한국어, 단일 섹터 (메모리 반도체)
  - 백테스트/Forward Conflict/시간 슬라이더 모두 V1+로 이연
  - 시간 슬라이더 없이 **고정 분기 1개** (예: 2024Q3)만 표시

---

## 9. Tier 2 데이터 수집 전략 (Q2 "무료 API only" 영향)

> **사용자 결정**: 어닝스 콜 트랜스크립트 유료 API 미사용. 무료 + 자체 수집으로 대체.

**전략: "공시 위주 + 보조적 가이던스" 조합**

### 9.1. Tier 2 보강 무료 소스 (Phase 2부터)

| 소스 | 종류 | 품질 | 비고 |
|---|---|---|---|
| **DART "영업실적공시"** | 정기 공시 | ★★★★★ | 한국 기업 분기 잠정실적 → 가이던스가 아닌 확정값 |
| **SEC 8-K** | 정기 공시 | ★★★★★ | 미국 기업 어닝 발표 자료 (PDF/HTML), 가이던스 포함 |
| **기업 IR 페이지 직접** | 직접 수집 | ★★★★☆ | 삼성/SK하이닉스/마이크론 모두 자체 IR에 컨콜 자료 PDF 공개 |
| **DART "주요사항보고서"** | 자율 공시 | ★★★★☆ | 단가/수주 변경 등 비정기 공시 |
| **Naver 증권 종목 분석** | 메타 | ★★★☆☆ | 컨콜 요약/리포트 링크 모음 |
| **자체 STT (Whisper)** | 직접 수집 | ★★★☆☆ | 기업이 IR 페이지에 공개한 어닝 콜 오디오를 Whisper로 변환 - **합법 (공개 자료)** |
| **YouTube 자동 캡션** | 직접 수집 | ★★☆☆☆ | 일부 기업 컨콜 영상이 YouTube에 있음. 캡션 활용 |

### 9.2. ToS-Safe 수집 원칙
- **금지**: SeekingAlpha/Yahoo Finance 트랜스크립트 페이지 스크래핑 (paywall 우회 = ToS 위반)
- **허용**: 회사가 IR 페이지에 직접 공개한 PDF/오디오 다운로드
- **허용**: 정부 공시 시스템(DART, EDGAR) API 호출 (rate limit 준수)
- **검증**: 모든 수집 코드에 source_url + 수집 시 robots.txt 준수 검사

### 9.3. Phase 2 데이터 파이프라인
```
[기업 IR 페이지 크롤러] (Playwright + Cheerio)
    ↓
[PDF 텍스트 추출] (PyMuPDF) / [오디오 → STT] (whisper.cpp)
    ↓
[Gemini로 가이던스 추출] (구조화된 JSON: metric, value, time_horizon, confidence)
    ↓
[citation 첨부 후 guidance_records 테이블 저장]
```

---

## 10. Phase 1 MVP 구체 작업 분해 (4주 기준, atomic + QA)

> **MVP 성공 정의 (Q7)**: "메모리 반도체 섹터에서 SK하이닉스 → 마이크론 같은 1개 엣지에 대해, 양사 공시 매출/매입 데이터를 자동 수집하고, 정합성을 검증하며, 출처가 첨부된 그래프 1개를 시각화"

> **태스크 형식**: 각 태스크는 (1) 생성/수정 파일 (2) 실행 단계 (3) QA 시나리오로 구성. QA는 도구/명령/예상 결과를 명시.

---

### Week 1: 인프라 + 데이터 수집 골격

#### T1.1. Monorepo 구조 셋업 (반나절)
**파일/디렉토리 생성**:
- `package.json` (root)
- `pnpm-workspace.yaml`
- `apps/web/` (Next.js 16)
- `apps/api/` (FastAPI)
- `packages/shared/` (TypeScript 타입)
- `.gitignore` (node_modules, __pycache__, .env, .next, dist 추가)
- `.env.example` (DART_API_KEY, SEC_USER_AGENT, SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY)
- `README.md` (셋업 방법)

**실행 단계**:
1. `pnpm init` (root)
2. `pnpm-workspace.yaml`에 `["apps/*", "packages/*"]` 정의
3. `mkdir apps/web apps/api packages/shared`
4. `apps/web/package.json` 초기화 (`name: "@valuechain/web"`)
5. `apps/api/pyproject.toml` 초기화 (uv 또는 poetry)
6. `packages/shared/package.json` 초기화 (`name: "@valuechain/shared"`)

**QA 시나리오**:
- 도구: pnpm, ls, git
- 명령:
  ```powershell
  pnpm install
  pnpm -r list --depth 0
  git status
  ```
- 예상 결과:
  - `pnpm install` 종료 코드 0
  - `pnpm -r list`에 `@valuechain/web`, `@valuechain/api`(N/A, python), `@valuechain/shared` 표시
  - `git status` clean (.env 제외, .gitignore 동작 확인)
- 합격 기준: 위 3개 모두 통과

---

#### T1.2. Supabase 프로젝트 + 스키마 마이그레이션 (1일)
**파일 생성**:
- `apps/api/supabase/migrations/0001_initial_schema.sql`
- `apps/api/supabase/seed.sql` (메모리 반도체 7개 기업 시드)
- `apps/api/.env.local` (Supabase 로컬 키)

**실행 단계**:
1. `npx supabase init` (apps/api 내부)
2. `npx supabase start` (로컬 Postgres 기동)
3. `0001_initial_schema.sql` 작성:
   ```sql
   create extension if not exists vector;

   create table companies (
     id uuid primary key default gen_random_uuid(),
     ticker text not null,
     name text not null,
     country text not null check (country in ('KR', 'US', 'JP', 'TW', 'CN')),
     sector text not null,
     workspace_id uuid not null default gen_random_uuid(), -- V2 multi-tenant 대비
     created_at timestamptz default now()
   );
   create unique index on companies (ticker, country);

   create table edges (
     id uuid primary key default gen_random_uuid(),
     supplier_id uuid not null references companies(id),
     buyer_id uuid not null references companies(id),
     product_category text not null,
     lag_quarters integer default 0,
     created_at timestamptz default now()
   );

   create table citations (
     id uuid primary key default gen_random_uuid(),
     source_url text not null,
     source_type text not null check (source_type in ('DART', 'EDGAR', 'CUSTOMS', 'IR_PDF', 'NEWS', 'EARNINGS_CALL')),
     source_tier integer not null check (source_tier between 1 and 3),
     publish_date date not null,
     disclosure_id text, -- DART rcept_no 등
     snippet text,
     embedding vector(768), -- Gemini text-embedding-004 차원
     created_at timestamptz default now()
   );
   create index on citations (publish_date);
   create unique index citations_dart_unique on citations (disclosure_id) where disclosure_id is not null;

   create table edge_metrics (
     id uuid primary key default gen_random_uuid(),
     edge_id uuid not null references edges(id),
     quarter text not null, -- '2024Q3' 형식
     price numeric,
     quantity numeric,
     revenue numeric,
     currency text not null default 'USD',
     is_imputed boolean default false,
     is_hypothesis boolean default false,
     confidence_score integer check (confidence_score between 1 and 100),
     created_at timestamptz default now()
   );
   create index on edge_metrics (edge_id, quarter);

   create table metric_citations (
     metric_id uuid references edge_metrics(id) on delete cascade,
     citation_id uuid references citations(id),
     weight numeric default 1.0,
     primary key (metric_id, citation_id)
   );

   create table runs (
     id uuid primary key default gen_random_uuid(),
     sector text not null,
     target_quarter text not null,
     status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
     started_at timestamptz default now(),
     completed_at timestamptz
   );
   ```
4. `seed.sql` 작성: 7개 기업 (Samsung Electronics, SK Hynix, Micron, Intel, NVIDIA, AMD, TSMC)
5. `npx supabase db reset` (마이그레이션 + 시드 적용)

**QA 시나리오**:
- 도구: psql, supabase CLI
- 명령:
  ```powershell
  npx supabase status
  npx supabase db dump --schema public > /tmp/schema.sql
  psql $env:DATABASE_URL -c "select count(*) from companies;"
  psql $env:DATABASE_URL -c "select tablename from pg_tables where schemaname='public';"
  ```
- 예상 결과:
  - `supabase status` API URL/Studio URL 표시 (정상)
  - `companies` 테이블 행수 = 7
  - `pg_tables`에 6개 테이블 (companies, edges, citations, edge_metrics, metric_citations, runs) 모두 존재
  - pgvector 확장 활성화 확인: `select * from pg_extension where extname='vector';` 행수 1
- 합격 기준: 위 4건 모두 통과

---

#### T1.3. FastAPI 골격 + Health 엔드포인트 + Railway 배포 (1일)
**파일 생성**:
- `apps/api/pyproject.toml` (의존성: fastapi, uvicorn, sse-starlette, supabase, pydantic, httpx)
- `apps/api/main.py` (FastAPI app entry)
- `apps/api/app/__init__.py`
- `apps/api/app/routes/health.py` (`GET /api/health`)
- `apps/api/app/routes/__init__.py`
- `apps/api/app/config.py` (env 로딩, pydantic-settings)
- `apps/api/Dockerfile`
- `apps/api/railway.json`
- `.github/workflows/api-deploy.yml` (선택: 자동 배포)

**실행 단계**:
1. `apps/api`에서 `uv init` 또는 `poetry init`
2. 의존성 설치: `uv add fastapi uvicorn[standard] sse-starlette supabase httpx pydantic-settings`
3. `main.py`:
   ```python
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   from app.routes import health

   app = FastAPI(title="ValueChain AI API", version="0.1.0")
   app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
   app.include_router(health.router, prefix="/api")
   ```
4. `health.py`:
   ```python
   from fastapi import APIRouter
   router = APIRouter()
   @router.get("/health")
   def health():
       return {"status": "ok", "service": "valuechain-api", "version": "0.1.0"}
   ```
5. `Dockerfile` (Railway용 standard Python image)
6. Railway 프로젝트 생성, GitHub repo 연결, 환경변수 설정
7. Push → 자동 배포 확인

**QA 시나리오**:
- 도구: uvicorn, curl, Railway dashboard
- 명령:
  ```powershell
  # 로컬
  uvicorn main:app --reload --port 8000
  curl http://localhost:8000/api/health
  # 원격 (Railway 배포 후)
  curl https://valuechain-api.up.railway.app/api/health
  ```
- 예상 결과:
  - 로컬: `{"status":"ok","service":"valuechain-api","version":"0.1.0"}`, HTTP 200
  - 원격: 동일 응답, HTTP 200, 응답시간 < 1s
  - Railway 대시보드: deploy status = success, no error logs
- 합격 기준: 로컬/원격 모두 health 응답 정상

---

#### T1.4. Next.js 16 골격 + 빈 React Flow 그래프 + Vercel 배포 (1일)
**파일 생성**:
- `apps/web/package.json` (next@16.2.4, react@19.2.4, tailwindcss@4, @xyflow/react, framer-motion)
- `apps/web/next.config.ts`
- `apps/web/tailwind.config.ts`
- `apps/web/postcss.config.js`
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx` (랜딩 - 추후 작업)
- `apps/web/app/dashboard/page.tsx` (메인 그래프 화면)
- `apps/web/app/globals.css` (Tailwind v4 import)
- `apps/web/components/graph/SupplyChainFlow.tsx` (빈 그래프 컴포넌트)
- `apps/web/vercel.json`

**실행 단계**:
1. `apps/web`에서 `pnpm create next-app@16.2.4 . --typescript --app --tailwind --no-eslint`
2. `pnpm add @xyflow/react framer-motion zustand @tanstack/react-query`
3. `SupplyChainFlow.tsx`:
   ```tsx
   'use client';
   import { ReactFlow, Background, Controls } from '@xyflow/react';
   import '@xyflow/react/dist/style.css';

   export function SupplyChainFlow() {
     return (
       <div className="h-[600px] w-full rounded-lg border">
         <ReactFlow nodes={[]} edges={[]}>
           <Background />
           <Controls />
         </ReactFlow>
       </div>
     );
   }
   ```
4. `app/dashboard/page.tsx`:
   ```tsx
   import { SupplyChainFlow } from '@/components/graph/SupplyChainFlow';
   export default function Dashboard() {
     return (
       <main className="container mx-auto p-8">
         <h1 className="mb-4 text-2xl font-bold">메모리 반도체 공급망</h1>
         <SupplyChainFlow />
       </main>
     );
   }
   ```
5. Vercel 프로젝트 생성, GitHub 연결, 환경변수 설정
6. Push → 자동 배포

**QA 시나리오**:
- 도구: pnpm, playwright (또는 수동), Vercel dashboard
- 명령:
  ```powershell
  cd apps/web
  pnpm dev # localhost:3000
  pnpm build # 프로덕션 빌드 검증
  ```
- 예상 결과:
  - `pnpm dev`: localhost:3000/dashboard 진입 시 빈 React Flow 그래프 + Background 격자 + Controls 표시
  - `pnpm build`: 종료 코드 0, "Compiled successfully" 출력, .next 디렉토리 생성
  - Vercel 배포 URL: 동일 화면, console error 0건
  - DevTools Network 탭: 200 응답만, 404/500 없음
- 합격 기준: 로컬/원격 모두 정상, 빌드 에러 0

---

#### T1.5. DART OpenAPI 어댑터 + SK하이닉스 매출/COGS 수집 (1일)
**파일 생성**:
- `apps/api/app/sources/__init__.py`
- `apps/api/app/sources/dart.py` (DART API 클라이언트)
- `apps/api/app/sources/types.py` (Pydantic 모델)
- `apps/api/app/db/__init__.py`
- `apps/api/app/db/supabase.py` (클라이언트 래퍼)
- `apps/api/scripts/fetch_skhynix.py` (1회성 스크립트)
- `apps/api/tests/test_dart.py`

**실행 단계**:
1. https://opendart.fss.or.kr 가입, API 키 발급, `.env`에 `DART_API_KEY` 저장
2. `dart.py`:
   ```python
   import httpx
   from datetime import date
   from app.sources.types import DartFinancialData, Citation

   class DartClient:
       BASE_URL = "https://opendart.fss.or.kr/api"

       def __init__(self, api_key: str):
           self.api_key = api_key
           self.client = httpx.AsyncClient(timeout=30.0)

       async def get_corp_code(self, ticker: str) -> str:
           """티커로 corp_code 조회 (별도 캐시 권장)"""
           ...

       async def get_financial_statements(self, corp_code: str, year: int, reprt_code: str) -> DartFinancialData:
           """단일회사 주요계정 (revenue, cogs 추출)
           reprt_code: 11013(1Q), 11012(반기), 11014(3Q), 11011(사업)
           """
           url = f"{self.BASE_URL}/fnlttSinglAcntAll.json"
           params = {
               "crtfc_key": self.api_key,
               "corp_code": corp_code,
               "bsns_year": str(year),
               "reprt_code": reprt_code,
               "fs_div": "CFS"  # 연결재무제표
           }
           response = await self.client.get(url, params=params)
           response.raise_for_status()
           data = response.json()
           # status '000' = 정상, '013' = 데이터 없음
           if data["status"] != "000":
               raise ValueError(f"DART error: {data['message']}")
           return self._parse_financial_data(data["list"], year, reprt_code)
   ```
3. `fetch_skhynix.py` 스크립트: SK하이닉스 corp_code 하드코드, 2024 1~3Q 데이터 수집 → DB 저장 (citations 행 생성, edge_metrics 입력 준비)
4. `tests/test_dart.py`: VCR 또는 mock으로 응답 stub, 파싱 단위 테스트

**QA 시나리오**:
- 도구: pytest, psql, python script
- 명령:
  ```powershell
  cd apps/api
  pytest tests/test_dart.py -v
  python scripts/fetch_skhynix.py
  psql $env:DATABASE_URL -c "select source_url, source_tier, publish_date, disclosure_id from citations where source_type='DART';"
  ```
- 예상 결과:
  - `pytest`: 모든 테스트 PASS, coverage > 70%
  - `fetch_skhynix.py`: 종료 코드 0, "Fetched 3 quarters for SK Hynix" 출력
  - DB 쿼리: 최소 3행 (각 분기당 1개), source_tier=1, disclosure_id (rcept_no) 채워짐
  - 각 citation의 source_url 형식: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}` 검증
- 합격 기준: pytest 통과 + DB에 실제 SK하이닉스 매출/COGS 값 (수십조원 KRW) 저장

---

#### T1.6. SEC EDGAR 어댑터 + 마이크론 매출/COGS 수집 (1일)
**파일 생성**:
- `apps/api/app/sources/edgar.py`
- `apps/api/scripts/fetch_micron.py`
- `apps/api/tests/test_edgar.py`

**실행 단계**:
1. SEC EDGAR User-Agent 등록 (이메일 포함, `.env`에 `SEC_USER_AGENT`)
2. `edgar.py`:
   ```python
   import httpx
   class EdgarClient:
       BASE_URL = "https://data.sec.gov"

       def __init__(self, user_agent: str):
           self.client = httpx.AsyncClient(headers={"User-Agent": user_agent}, timeout=30.0)

       async def get_company_facts(self, cik: str) -> dict:
           """XBRL 재무제표 전체 facts (us-gaap:Revenues, us-gaap:CostOfRevenue)"""
           cik_padded = cik.zfill(10)
           url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"
           response = await self.client.get(url)
           response.raise_for_status()
           return response.json()

       def extract_quarterly(self, facts: dict, concept: str, year: int, quarter: int) -> Optional[float]:
           """us-gaap:Revenues에서 특정 분기 값 추출 (10-Q form)"""
           ...
   ```
3. Micron CIK = 0000723125. 2024 분기별 Revenue, CostOfRevenue 추출
4. `fetch_micron.py` 실행 → DB에 citations + 매출/COGS 저장

**QA 시나리오**:
- 도구: pytest, psql, python
- 명령:
  ```powershell
  pytest tests/test_edgar.py -v
  python scripts/fetch_micron.py
  psql $env:DATABASE_URL -c "select source_url, publish_date from citations where source_type='EDGAR';"
  ```
- 예상 결과:
  - 최소 3행 citations (FY24 Q1/Q2/Q3, Micron 회계연도 8월 마감)
  - source_url 형식: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000723125...`
  - 매출 값: 수십억 USD 범위
- 합격 기준: pytest 통과 + DB에 실제 Micron 데이터 저장

---

#### T1.7. FX rate API 어댑터 (KRW/USD 분기 평균) (반나절)
**파일 생성**:
- `apps/api/app/sources/fx.py` (한국은행 ECOS API 또는 ExchangeRate-API)
- `apps/api/scripts/fetch_fx.py`
- `apps/api/tests/test_fx.py`

**실행 단계**:
1. 한국은행 ECOS (https://ecos.bok.or.kr) API 키 발급, 통계코드 731Y004 (원/달러 환율) 조회
2. `fx.py`: 분기별 일평균 환율의 평균 산출 (3개월간 영업일 평균)
3. `fetch_fx.py` 실행 → 2022Q1 ~ 2024Q4 KRW/USD 분기 평균 환율 수집

**QA 시나리오**:
- 도구: pytest, psql
- 명령:
  ```powershell
  pytest tests/test_fx.py -v
  python scripts/fetch_fx.py
  psql $env:DATABASE_URL -c "select * from fx_rates where currency_pair='KRW/USD' order by quarter;"
  ```
- 예상 결과:
  - 12행 (3년 × 4분기), 환율 값 1100~1450 범위 (실제 분기 평균)
  - 2022Q4 ~1380, 2024Q3 ~1340 정도 (역사적 검증)
- 합격 기준: 12행 모두 정상, 값 범위 검증 통과

---

### Week 2: 멀티 에이전트 골격

#### T2.1. LangGraph 셋업 + PostgresSaver + State 정의 (1일)
**파일 생성**:
- `apps/api/app/agents/__init__.py`
- `apps/api/app/agents/state.py` (PipelineState TypedDict)
- `apps/api/app/agents/graph.py` (StateGraph 정의)
- `apps/api/app/agents/nodes/__init__.py` (4개 빈 노드)

**실행 단계**:
1. 의존성: `uv add langgraph langgraph-checkpoint-postgres langchain-google-genai`
2. `state.py`:
   ```python
   from typing import TypedDict, Optional, Literal
   from datetime import datetime

   class PipelineState(TypedDict):
       sector: str
       target_quarter: str
       as_of_date: datetime
       is_backtest: bool
       topology: Optional[dict]
       raw_data: Optional[dict]
       quantified: Optional[dict]
       reconciliation_errors: list
       confidence_map: dict
       trace_events: list  # SSE 송출용 사고 이벤트
   ```
3. `graph.py`: StateGraph 만들고 PostgresSaver를 Supabase 직결
4. 4개 빈 노드: 각각 print + state 패스스루만 (다음 태스크에서 채움)

**QA 시나리오**:
- 도구: pytest, python REPL
- 명령:
  ```python
  from app.agents.graph import build_graph
  graph = build_graph()
  result = await graph.ainvoke({
      "sector": "memory_semiconductor",
      "target_quarter": "2024Q3",
      "as_of_date": datetime(2024, 11, 30),
      "is_backtest": False,
      "topology": None, "raw_data": None, "quantified": None,
      "reconciliation_errors": [], "confidence_map": {}, "trace_events": []
  }, config={"configurable": {"thread_id": "test-1"}})
  print(result)
  ```
- 예상 결과:
  - 4개 노드 모두 통과, 에러 없음
  - `result["trace_events"]`에 4개 이벤트
  - PostgresSaver: `select count(*) from langgraph_checkpoints;` ≥ 4
- 합격 기준: 빈 그래프 정상 실행 + 체크포인트 저장 확인

---

#### T2.2. Structure Mapper 노드 (메모리 반도체 토폴로지 하드코드) (반나절)
**파일 생성**:
- `apps/api/app/agents/nodes/structure_mapper.py`
- `apps/api/app/agents/topology/memory_semi.py` (정적 토폴로지)

**실행 단계**:
1. `topology/memory_semi.py`:
   ```python
   MEMORY_SEMICONDUCTOR_TOPOLOGY = {
       "nodes": [
           {"ticker": "005930.KS", "name": "Samsung Electronics", "country": "KR"},
           {"ticker": "000660.KS", "name": "SK Hynix", "country": "KR"},
           {"ticker": "MU", "name": "Micron Technology", "country": "US"},
           {"ticker": "NVDA", "name": "NVIDIA", "country": "US"},
           {"ticker": "AMD", "name": "AMD", "country": "US"},
           {"ticker": "INTC", "name": "Intel", "country": "US"},
           {"ticker": "TSM", "name": "TSMC", "country": "TW"},
       ],
       "edges": [
           {"supplier": "000660.KS", "buyer": "NVDA", "product": "HBM", "lag_quarters": 1},
           {"supplier": "005930.KS", "buyer": "NVDA", "product": "HBM", "lag_quarters": 1},
           {"supplier": "MU", "buyer": "NVDA", "product": "HBM", "lag_quarters": 1},
           # ... 10여개 엣지
       ]
   }
   ```
2. `structure_mapper.py`: 토폴로지를 state["topology"]에 채우고 trace_events 추가

**QA 시나리오**:
- 도구: pytest
- 명령: `pytest tests/test_structure_mapper.py -v`
- 예상 결과:
  - state["topology"]["nodes"] 길이 = 7
  - state["topology"]["edges"] 길이 ≥ 10
  - 모든 edge의 supplier/buyer는 nodes에 존재 (참조 무결성)
- 합격 기준: 노드/엣지 수 일치, 무결성 검증 통과

---

#### T2.3. Data Collector 노드 (DART/EDGAR 어댑터 호출) (1일)
**파일 생성**:
- `apps/api/app/agents/nodes/data_collector.py`
- `apps/api/tests/test_data_collector.py`

**실행 단계**:
1. 토폴로지 노드 순회 → DART/EDGAR 어댑터 호출 → companies 매핑 → DB upsert
2. citation 자동 생성 + state["raw_data"]에 채움
3. 각 단계마다 trace_event emit

**QA 시나리오**:
- 도구: pytest, psql
- 명령:
  ```powershell
  pytest tests/test_data_collector.py -v
  psql $env:DATABASE_URL -c "select count(*) from citations;"
  psql $env:DATABASE_URL -c "select c.ticker, em.quarter, em.revenue from edge_metrics em join edges e on em.edge_id=e.id join companies c on e.supplier_id=c.id where em.quarter='2024Q3';"
  ```
- 예상 결과:
  - citations 행수 ≥ 7 (각 회사 1건 이상)
  - edge_metrics에 2024Q3 행 ≥ 5
  - 모든 metric에 metric_citations 연결 확인
- 합격 기준: 자동 수집 → DB 저장 → citations 첨부 모두 정상

---

#### T2.4. Pydantic GroundedNumber + 검증 미들웨어 (반나절)
**파일 생성**:
- `apps/api/app/schemas/grounded.py`
- `apps/api/app/services/validation.py`
- `apps/api/tests/test_grounded.py`

**실행 단계**:
1. `grounded.py`:
   ```python
   from pydantic import BaseModel, Field
   from typing import Literal
   from uuid import UUID

   class GroundedNumber(BaseModel):
       value: float
       currency: Literal["USD", "KRW", "JPY", "TWD", "CNY"]
       citation_ids: list[UUID] = Field(min_length=1)
       is_hypothesis: bool = False
       confidence: int = Field(ge=1, le=100)
   ```
2. `validation.py`: citation_ids가 모두 DB에 존재하는지, publish_date <= as_of_date인지 검증

**QA 시나리오**:
- 도구: pytest
- 명령: `pytest tests/test_grounded.py -v`
- 예상 결과:
  - citation_ids 빈 리스트 → ValidationError
  - 가공 UUID → GroundingError
  - publish_date > as_of_date → TimeIsolationError
- 합격 기준: 3가지 에러 케이스 모두 차단

---

#### T2.5. Quant Estimator 노드 (P×Q 계산, 결측치 역산) (1일)
**파일 생성**:
- `apps/api/app/agents/nodes/quant_estimator.py`
- `apps/api/app/services/imputation.py`
- `apps/api/tests/test_quant.py`

**실행 단계**:
1. raw_data에서 각 엣지의 P, Q 시도 → 둘 다 있으면 Revenue = P × Q
2. P 또는 Q 결측 시 시장점유율 + 총매출로 역산, is_imputed=True 마킹
3. 통화 환산: FX rate로 USD 통일
4. state["quantified"] 채움

**QA 시나리오**:
- 도구: pytest, 수동 검증
- 명령:
  ```powershell
  pytest tests/test_quant.py -v
  # 수동: SK하이닉스 2024Q3 HBM 매출이 NVIDIA 가이던스 대비 ±20% 이내인지
  ```
- 예상 결과:
  - 모든 엣지에 revenue 채워짐 (USD)
  - 결측 역산은 is_imputed=True로 명시
  - 통화 단위 일관성 (모두 USD)
- 합격 기준: 수치적 sanity check 통과 (제3자 리포트 대조)

---

#### T2.6. Evaluator 노드 - Reconciliation만 (반나절)
**파일 생성**:
- `apps/api/app/agents/nodes/evaluator.py`
- `apps/api/app/services/reconciliation.py`
- `apps/api/tests/test_reconciliation.py`

**실행 단계**:
1. 각 엣지에 대해: A의 매출(B향) ≈ B의 매입(A향) 검증
2. 시차 lag_quarters 적용
3. 오차율 > 10%면 reconciliation_errors에 추가
4. B의 sum(매입) <= B's COGS 검증

**QA 시나리오**:
- 도구: pytest
- 명령: `pytest tests/test_reconciliation.py -v`
- 예상 결과:
  - 단순 일치 케이스: errors 0건
  - 의도적 오차 주입: errors에 정확히 1건
  - lag_quarters=1 적용 검증: 같은 분기로 비교하지 않음
- 합격 기준: 정합성 검증 로직 정확

---

### Week 3: 스트리밍 + UI

#### T3.1. FastAPI SSE 엔드포인트 + LangGraph 스트림 변환 (1일)
**파일 생성**:
- `apps/api/app/routes/runs.py` (`POST /api/runs`, `GET /api/runs/:id/stream`)
- `apps/api/app/services/stream.py`
- `apps/api/tests/test_stream.py`

**실행 단계**:
1. `runs.py`:
   ```python
   from sse_starlette.sse import EventSourceResponse
   from app.agents.graph import build_graph

   @router.post("/runs")
   async def create_run(payload: RunCreate) -> RunCreated:
       run_id = create_run_in_db(payload.sector, payload.target_quarter)
       return {"run_id": run_id}

   @router.get("/runs/{run_id}/stream")
   async def stream_run(run_id: str):
       async def event_gen():
           graph = build_graph()
           async for event in graph.astream_events({...}, config={...}, version="v2"):
               yield {"event": event["event"], "data": json.dumps(event["data"])}
       return EventSourceResponse(event_gen())
   ```

**QA 시나리오**:
- 도구: curl, pytest with httpx
- 명령:
  ```powershell
  curl -N "http://localhost:8000/api/runs/test-id/stream"
  pytest tests/test_stream.py -v
  ```
- 예상 결과:
  - curl: SSE 청크 스트리밍, `event:` `data:` 포맷 정상
  - 최종 이벤트 = "completed"
  - 30초 이내 종료
- 합격 기준: SSE 포맷 RFC 준수, 끊김 없음

---

#### T3.2. React Flow CompanyNode + TradeEdge 커스텀 컴포넌트 (1일)
**파일 생성**:
- `apps/web/components/graph/CompanyNode.tsx`
- `apps/web/components/graph/TradeEdge.tsx`
- `apps/web/components/graph/SupplyChainFlow.tsx` (업데이트)
- `apps/web/lib/format.ts` (숫자/통화 포맷)

**실행 단계**:
1. `CompanyNode.tsx`: 매출 → 노드 크기, 신뢰도 → 색상, 티커/이름 표시
2. `TradeEdge.tsx`: 물량 → 두께, 정합성 오차 → 색상, hover 시 tooltip
3. `SupplyChainFlow.tsx`: nodeTypes/edgeTypes 등록

**QA 시나리오**:
- 도구: playwright, 수동 시각 검증
- 명령:
  ```powershell
  pnpm test:e2e graph.spec.ts
  pnpm dev # 수동 확인
  ```
- 예상 결과:
  - SK하이닉스 노드가 마이크론 노드보다 큼 (매출 차)
  - 엣지 hover 시 tooltip 표시
  - 정합성 오차 엣지는 노란색
- 합격 기준: 시각 sanity + playwright 통과

---

#### T3.3. SSE Hook + ThoughtPanel + CitationCard (1일)
**파일 생성**:
- `apps/web/hooks/useAgentStream.ts`
- `apps/web/components/agent-stream/ThoughtPanel.tsx`
- `apps/web/components/agent-stream/CitationCard.tsx`
- `apps/web/lib/sse-client.ts` (microsoft/fetch-event-source 래퍼)

**실행 단계**:
1. `pnpm add @microsoft/fetch-event-source`
2. `useAgentStream.ts`: 이벤트 큐 + 상태 관리
3. `ThoughtPanel.tsx`: 4개 에이전트 칼럼, 실시간 사고 표시
4. `CitationCard.tsx`: source_url, snippet, publish_date 표시

**QA 시나리오**:
- 도구: playwright
- 명령: `pnpm test:e2e dashboard.spec.ts`
- 시나리오:
  1. 사용자가 "Run" 버튼 클릭
  2. SSE 연결 → ThoughtPanel에 4개 에이전트 카드 등장
  3. 5초 내 첫 사고 청크 등장
  4. 30초 내 완료 + 그래프 렌더링
- 합격 기준: E2E 테스트 통과 + 끊김 없는 스트림

---

#### T3.4. 정합성 오차 시각화 + 출처 hover (반나절)
**파일 생성**:
- `apps/web/components/graph/EdgeTooltip.tsx`
- `apps/web/components/graph/ReconciliationLegend.tsx`

**실행 단계**:
1. 엣지 색상: 오차율 0~5%=초록, 5~10%=노랑, 10%+=주황
2. Hover tooltip: A 매출, B 매입, 오차율, citation_ids → CitationCard

**QA 시나리오**:
- 도구: playwright + 시각 검증
- 명령: `pnpm test:e2e edge-tooltip.spec.ts`
- 합격 기준: 색상 mapping 정확, tooltip 정상

---

### Week 4: 마무리 + 검증

#### T4.1. E2E 시나리오: "메모리 반도체 2024Q3" 워크플로우 (1일)
**파일 생성**:
- `apps/web/tests/e2e/mvp.spec.ts`

**실행 단계**:
1. 사용자 → Dashboard 진입 → "Memory Semi 2024Q3 분석" 클릭
2. SSE 연결 + ThoughtPanel 등장
3. 60초 내 그래프 + 출처 + 정합성 결과 표시
4. 엣지 hover → tooltip 정상

**QA 시나리오**:
- 도구: playwright (chrome + firefox + webkit)
- 명령: `pnpm test:e2e --project=chromium --project=firefox`
- 합격 기준:
  - TTFGraph (Time To First Graph) < 60s
  - 모든 엣지에 citation 1+ 첨부
  - 정합성 오차 결과 1건 이상 표시 (검증 작동 증거)

---

#### T4.2. 에러 처리 + Fallback (반나절)
**파일 생성**:
- `apps/api/app/middleware/error_handler.py`
- `apps/web/components/error/ErrorBoundary.tsx`
- `apps/web/components/error/AgentErrorPanel.tsx`

**실행 단계**:
1. DART API 401/429 → 친절한 에러 메시지
2. LLM 환각 (citation 가공) → 차단 + 사용자에게 표시
3. SSE 끊김 → 자동 재연결 (3회)

**QA 시나리오**:
- 도구: pytest, playwright
- 명령:
  ```powershell
  pytest tests/test_error_handler.py -v
  pnpm test:e2e error-cases.spec.ts
  ```
- 시나리오: API 키 무효화, citation 검증 실패, SSE 강제 끊김
- 합격 기준: 모든 에러 케이스에 우아한 fallback

---

#### T4.3. 데모 시드 데이터 + 성능 측정 (반나절)
**파일 생성**:
- `apps/api/scripts/seed_demo.py`
- `apps/api/scripts/benchmark.py`

**실행 단계**:
1. 2024Q3 데이터 미리 캐시 (cold start 방지)
2. TTFGraph, 첫 청크까지 시간 측정

**QA 시나리오**:
- 도구: 자체 benchmark 스크립트
- 명령: `python scripts/benchmark.py --runs 5`
- 예상 결과:
  - TTFGraph p50 < 30s, p95 < 60s
  - 첫 SSE 청크 < 3s
- 합격 기준: 위 SLA 충족

---

#### T4.4. 데모 자료 + 회고 (반나절)
**파일 생성**:
- `docs/MVP_DEMO.md` (시연 시나리오)
- `docs/RETROSPECTIVE.md` (V1로 가기 위한 학습)
- 데모 영상 (선택)

**QA 시나리오**:
- 도구: 사람 (대표/투자자/팀원)
- 시나리오: 5분 시연
- 합격 기준: 시청자가 "정합성 검증의 가치"를 1회 만에 이해

---

### Week 별 합격 기준 요약

| Week | 합격 기준 |
|---|---|
| 1 | 모든 외부 API 어댑터 정상, DB에 실제 데이터 저장, 인프라 배포 완료 |
| 2 | 4개 LangGraph 노드가 빈 그래프부터 정합성 검증까지 end-to-end 작동 |
| 3 | SSE 스트리밍 + 시각화 + 출처 표시 모두 작동, E2E 시나리오 1건 통과 |
| 4 | TTFGraph SLA 충족, 에러 처리 견고, 시연 가능 상태 |

---

## 11. 핵심 의존성 / 리스크 (v0.2 갱신)

### 의존성
- **Gemini API 키**: Google Cloud 결제 계정 필요
- **DART OpenAPI 키**: 무료 발급 (https://opendart.fss.or.kr)
- **SEC EDGAR**: 키 불필요 (User-Agent만 등록)
- **Supabase 무료 티어**: Phase 1엔 충분 (DB 500MB, Auth는 미사용)
- **Vercel 무료**: 가능
- **Railway/Render 무료/저비용**: $5~$10/월

### 신규 리스크 (Q2/Q6 결정으로 추가)
| 리스크 | 가능성 | 영향 | 완화 |
|---|---|---|---|
| 무료 데이터 소스 부족으로 Tier 2 가이던스 누락 | 높음 | 높음 | §9 다중 소스 조합. PDF 추출+STT 전략 |
| 12분기(3년) 백테스트 시 COVID-19 노이즈 | 높음 | 중 | Macro Shock 모드 (§Error Handling 3) 강화. 2020Q1~2021Q1을 별도 처리 |
| 메모리 다운사이클(2022~2023) 백테스트가 가이던스 과대추정 노출 | 높음 | 중 | 이는 **오히려 자가 진화 학습 기회** - 다운사이클 페널티 규칙의 정당성 입증 |
| IR PDF 포맷 변동성 | 중 | 중 | LLM 추출이 robust. 다만 추출 실패 시 fallback (수동 라벨) |
| 한국어 only로 글로벌 사용자 차단 | 낮음(MVP) | 낮음 | V2에서 i18n. shared format 라이브러리로 대비 |

---

## 12. 다음 단계 (v0.2 → v0.3 → v1.0)

1. ⏳ **리서치 4건 도착 대기** (React Flow / 데이터 API / 백테스트 / SSE)
2. 🔄 v0.3: 리서치 결과 도착 시 ADR-001/003/006/007 보강
3. 🔍 **Momus 리뷰** 자동 트리거 (`.sisyphus/plans/*.md` 감지)
4. 📝 v1.0: Momus 피드백 반영, 사용자 최종 확인
5. 🚀 사용자 GO 신호 → Week 1 todo breakdown을 todowrite 도구로 옮김 → 구현 착수

---

> **Status**: v0.2, 사용자 의사결정 반영 완료. 리서치 결과 도착 시 v0.3.
