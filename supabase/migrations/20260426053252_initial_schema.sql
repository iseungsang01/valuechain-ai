-- =====================================================================
-- ValueChain AI - Initial Schema (Phase 1 MVP)
-- =====================================================================
-- 설계 문서: .sisyphus/plans/valuechain-ai-architecture.md (v1.1, Momus 승인)
--
-- 핵심 원칙:
--   1. Mandatory Grounding - 모든 수치는 citations 참조 (FK)
--   2. Time Isolation - publish_date / created_at 분리 (백테스트 누설 방지)
--   3. Multi-tenancy ready - workspace_id 컬럼 처음부터 포함 (V2 준비)
--   4. RLS by default - public schema 모든 테이블에 RLS 활성화
--
-- Phase 1 RLS 정책: 정책 없음 = deny-all. backend의 service_role만 접근.
-- V2에서 사용자별 정책 추가 예정.
-- =====================================================================

-- pgvector: citation 임베딩용 (V1+ 활용)
create extension if not exists vector;
-- pgcrypto: gen_random_uuid()용
create extension if not exists pgcrypto;


-- =====================================================================
-- 1. companies - 기업 노드
-- =====================================================================
create table public.companies (
  id            uuid primary key default gen_random_uuid(),
  ticker        text not null,
  name          text not null,
  country       text not null check (country in ('KR', 'US', 'JP', 'TW', 'CN')),
  sector        text not null,
  workspace_id  uuid not null default gen_random_uuid(),
  created_at    timestamptz not null default now()
);

create unique index companies_ticker_country_uidx on public.companies (ticker, country);
create index companies_sector_idx on public.companies (sector);
create index companies_workspace_idx on public.companies (workspace_id);

alter table public.companies enable row level security;

comment on table public.companies is '기업 노드 (supply chain의 vertices)';
comment on column public.companies.workspace_id is 'V2 multi-tenancy 대비. Phase 1에선 단일값.';


-- =====================================================================
-- 2. edges - 공급망 엣지 (방향성: supplier -> buyer)
-- =====================================================================
create table public.edges (
  id                uuid primary key default gen_random_uuid(),
  supplier_id       uuid not null references public.companies(id) on delete cascade,
  buyer_id          uuid not null references public.companies(id) on delete cascade,
  product_category  text not null,
  -- 매출 인식 시차: 발주 -> 매출 인식까지의 분기 수 (예: 반도체 장비 ~2분기)
  lag_quarters      integer not null default 0 check (lag_quarters >= 0 and lag_quarters <= 8),
  workspace_id      uuid not null default gen_random_uuid(),
  created_at        timestamptz not null default now(),
  constraint edges_no_self_loop check (supplier_id <> buyer_id)
);

create index edges_supplier_idx on public.edges (supplier_id);
create index edges_buyer_idx on public.edges (buyer_id);
create unique index edges_unique_relationship
  on public.edges (supplier_id, buyer_id, product_category);

alter table public.edges enable row level security;

comment on table public.edges is '공급망 엣지 (B2B 납품 관계). supplier -> buyer 방향성';
comment on column public.edges.lag_quarters is '발주~매출 인식 시차 (분기). reconciliation에서 시차 보정 적용';


-- =====================================================================
-- 3. citations - 출처 (Mandatory Grounding 핵심)
-- =====================================================================
create table public.citations (
  id              uuid primary key default gen_random_uuid(),
  source_url      text not null,
  source_type     text not null check (source_type in (
    'DART',           -- 한국 전자공시
    'EDGAR',          -- 미국 SEC 공시
    'CUSTOMS',        -- 한국 관세청 (HS code)
    'IR_PDF',         -- 기업 IR 페이지 직접 PDF
    'NEWS',           -- 뉴스 기사
    'EARNINGS_CALL'   -- 어닝 콜 (자체 STT 포함)
  )),
  source_tier     integer not null check (source_tier between 1 and 3),
  -- 시점 격리(Time Isolation): publish_date <= as_of_date 검증
  publish_date    date not null,
  -- DART rcept_no, EDGAR accession number 등
  disclosure_id   text,
  snippet         text,
  -- Gemini text-embedding-004 = 768차원
  embedding       vector(768),
  workspace_id    uuid not null default gen_random_uuid(),
  created_at      timestamptz not null default now()
);

create index citations_publish_date_idx on public.citations (publish_date);
create index citations_source_type_idx on public.citations (source_type);
create unique index citations_disclosure_unique_uidx
  on public.citations (disclosure_id)
  where disclosure_id is not null and source_type in ('DART', 'EDGAR');

create index citations_embedding_hnsw_idx
  on public.citations
  using hnsw (embedding vector_cosine_ops);

alter table public.citations enable row level security;

comment on table public.citations is 'Mandatory Grounding: 모든 수치는 1개 이상의 citation 참조 필수';
comment on column public.citations.publish_date is '원천 공개 날짜. 백테스트 시 as_of_date 이후 차단';
comment on column public.citations.source_tier is '1=공시(최우선), 2=가이던스, 3=참고. 충돌 시 낮은 tier 채택';


-- =====================================================================
-- 4. edge_metrics - 분기별 거래 수치 (시계열)
-- =====================================================================
create table public.edge_metrics (
  id                uuid primary key default gen_random_uuid(),
  edge_id           uuid not null references public.edges(id) on delete cascade,
  quarter           text not null check (quarter ~ '^[0-9]{4}Q[1-4]$'),
  price             numeric(20, 4),
  quantity          numeric(20, 4),
  revenue           numeric(20, 4),
  currency          text not null default 'USD'
                    check (currency in ('USD', 'KRW', 'JPY', 'TWD', 'CNY')),
  is_imputed        boolean not null default false,
  is_hypothesis     boolean not null default false,
  confidence_score  integer check (confidence_score between 1 and 100),
  workspace_id      uuid not null default gen_random_uuid(),
  created_at        timestamptz not null default now()
);

create unique index edge_metrics_edge_quarter_uidx
  on public.edge_metrics (edge_id, quarter);
create index edge_metrics_quarter_idx on public.edge_metrics (quarter);
create index edge_metrics_created_idx on public.edge_metrics (created_at);

alter table public.edge_metrics enable row level security;

comment on table public.edge_metrics is '분기별 P, Q, Revenue. 통화는 currency 컬럼 명시';
comment on column public.edge_metrics.is_hypothesis is 'true이면 UI에서 점선/회색 표시';


-- =====================================================================
-- 5. metric_citations - metric <-> citation 다대다
-- =====================================================================
create table public.metric_citations (
  metric_id   uuid not null references public.edge_metrics(id) on delete cascade,
  citation_id uuid not null references public.citations(id) on delete restrict,
  weight      numeric(5, 4) not null default 1.0 check (weight > 0 and weight <= 1),
  primary key (metric_id, citation_id)
);

create index metric_citations_citation_idx on public.metric_citations (citation_id);

alter table public.metric_citations enable row level security;

comment on table public.metric_citations is 'Mandatory Grounding 강제 - 모든 metric은 citation 1개 이상 연결';


-- =====================================================================
-- 6. fx_rates - 분기별 평균 환율 (Currency Synchronization)
-- =====================================================================
create table public.fx_rates (
  id              uuid primary key default gen_random_uuid(),
  -- 'KRW/USD' = 1 USD를 KRW로 환산 (KRW 단위)
  currency_pair   text not null check (currency_pair ~ '^[A-Z]{3}/[A-Z]{3}$'),
  quarter         text not null check (quarter ~ '^[0-9]{4}Q[1-4]$'),
  rate            numeric(20, 6) not null check (rate > 0),
  source_url      text not null,
  source_name     text not null default 'BOK_ECOS',
  created_at      timestamptz not null default now()
);

create unique index fx_rates_pair_quarter_uidx
  on public.fx_rates (currency_pair, quarter);
create index fx_rates_quarter_idx on public.fx_rates (quarter);

alter table public.fx_rates enable row level security;

comment on table public.fx_rates is '분기별 평균 환율. 통화 단일화(USD 환산) 시 사용';


-- =====================================================================
-- 7. runs - 에이전트 파이프라인 실행 추적
-- =====================================================================
create table public.runs (
  id              uuid primary key default gen_random_uuid(),
  sector          text not null,
  target_quarter  text not null check (target_quarter ~ '^[0-9]{4}Q[1-4]$'),
  is_backtest     boolean not null default false,
  -- 시점 격리 핵심: 이 시점 이후의 데이터는 보지 않음
  as_of_date      timestamptz not null default now(),
  status          text not null default 'pending'
                  check (status in ('pending', 'running', 'completed', 'failed')),
  total_edges_processed   integer,
  reconciliation_errors   integer,
  workspace_id            uuid not null default gen_random_uuid(),
  started_at              timestamptz not null default now(),
  completed_at            timestamptz,
  error_message           text
);

create index runs_status_idx on public.runs (status);
create index runs_started_idx on public.runs (started_at desc);

alter table public.runs enable row level security;

comment on table public.runs is '파이프라인 실행 추적. is_backtest=true면 as_of_date 이후 데이터 차단';


-- =====================================================================
-- 8. trace_events - 에이전트 사고 이벤트 (SSE 스트림 영속화)
-- =====================================================================
create table public.trace_events (
  id          uuid primary key default gen_random_uuid(),
  run_id      uuid not null references public.runs(id) on delete cascade,
  agent       text not null check (agent in (
    'StructureMapper', 'DataCollector', 'QuantEstimator', 'Evaluator'
  )),
  event_type  text not null check (event_type in (
    'agent_start', 'thought', 'tool_call', 'tool_result',
    'graph_update', 'agent_complete', 'pipeline_complete', 'error'
  )),
  payload     jsonb not null,
  created_at  timestamptz not null default now()
);

create index trace_events_run_idx on public.trace_events (run_id, created_at);

alter table public.trace_events enable row level security;

comment on table public.trace_events is 'SSE 스트림 영속화. UI에서 과거 run의 사고 과정 재생 가능';


-- =====================================================================
-- 방어 심화: anon/authenticated 권한 명시적 회수
-- (RLS deny-all + 명시적 revoke 이중 차단)
-- =====================================================================
revoke all on public.companies        from anon, authenticated;
revoke all on public.edges            from anon, authenticated;
revoke all on public.citations        from anon, authenticated;
revoke all on public.edge_metrics     from anon, authenticated;
revoke all on public.metric_citations from anon, authenticated;
revoke all on public.fx_rates         from anon, authenticated;
revoke all on public.runs             from anon, authenticated;
revoke all on public.trace_events     from anon, authenticated;
