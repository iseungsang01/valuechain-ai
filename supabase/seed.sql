-- =====================================================================
-- ValueChain AI - Seed Data (Phase 1 MVP)
-- =====================================================================
-- 메모리 반도체 섹터 7개 핵심 기업 시드
-- 적용: psql ... -f supabase/seed.sql 또는 supabase db reset 시 자동
-- =====================================================================

-- 단일 workspace ID (Phase 1은 단일 사용자)
-- 향후 V2에서 사용자별로 분리
do $$
declare
  ws_id uuid := '00000000-0000-0000-0000-000000000001';
begin
  -- 7개 기업 (DART/EDGAR 모두 풍부, 메모리 반도체 supply chain 핵심)
  insert into public.companies (ticker, name, country, sector, workspace_id) values
    ('005930.KS', 'Samsung Electronics',  'KR', 'memory_semiconductor', ws_id),
    ('000660.KS', 'SK Hynix',             'KR', 'memory_semiconductor', ws_id),
    ('MU',        'Micron Technology',    'US', 'memory_semiconductor', ws_id),
    ('NVDA',      'NVIDIA',               'US', 'memory_semiconductor', ws_id),
    ('AMD',       'AMD',                  'US', 'memory_semiconductor', ws_id),
    ('INTC',      'Intel',                'US', 'memory_semiconductor', ws_id),
    ('TSM',       'TSMC',                 'TW', 'memory_semiconductor', ws_id);

  -- 메모리 반도체 supply chain 엣지 (HBM, DRAM 중심)
  -- HBM: SK Hynix/Samsung/Micron -> NVIDIA/AMD (HBM = AI GPU 필수)
  -- DRAM: Samsung/SK Hynix/Micron -> Intel (서버용)
  -- Foundry: TSMC -> NVIDIA/AMD (CoWoS 패키징 포함)
  insert into public.edges (supplier_id, buyer_id, product_category, lag_quarters, workspace_id)
  select s.id, b.id, e.product_category, e.lag_quarters, ws_id
  from (values
    ('000660.KS', 'NVDA', 'HBM',          1),  -- SK Hynix -> NVIDIA HBM3/HBM3E
    ('005930.KS', 'NVDA', 'HBM',          1),  -- Samsung -> NVIDIA HBM
    ('MU',        'NVDA', 'HBM',          1),  -- Micron -> NVIDIA HBM
    ('000660.KS', 'AMD',  'HBM',          1),  -- SK Hynix -> AMD MI300
    ('005930.KS', 'AMD',  'HBM',          1),
    ('000660.KS', 'INTC', 'DRAM_DDR5',    1),  -- 서버용 DDR5
    ('005930.KS', 'INTC', 'DRAM_DDR5',    1),
    ('MU',        'INTC', 'DRAM_DDR5',    1),
    ('TSM',       'NVDA', 'FOUNDRY_COWOS', 2), -- TSMC CoWoS 패키징
    ('TSM',       'AMD',  'FOUNDRY_COWOS', 2),
    ('TSM',       'INTC', 'FOUNDRY_5NM',   2)  -- Intel도 일부 TSMC 위탁
  ) as e(supplier_ticker, buyer_ticker, product_category, lag_quarters)
  join public.companies s on s.ticker = e.supplier_ticker
  join public.companies b on b.ticker = e.buyer_ticker
  where s.workspace_id = ws_id and b.workspace_id = ws_id;
end $$;
