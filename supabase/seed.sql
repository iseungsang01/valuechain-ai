-- =====================================================================
-- ValueChain AI - Seed Data (Phase 1 MVP)
-- =====================================================================
-- 메모리 반도체 섹터 13개 핵심 기업 시드 (장비 + 메모리/Foundry + 팹리스/OEM)
-- 적용: psql ... -f supabase/seed.sql 또는 supabase db reset 시 자동
-- =====================================================================

-- 단일 workspace ID (Phase 1은 단일 사용자)
-- 향후 V2에서 사용자별로 분리
do $$
declare
  ws_id uuid := '00000000-0000-0000-0000-000000000001';
begin
  -- 13개 기업 - upstream(장비)·midstream(메모리/Foundry)·downstream(OEM/팹리스) 전체
  -- DART/EDGAR(US/TW), AEX(NL ASML) 모두 데이터 풍부
  insert into public.companies (ticker, name, country, sector, workspace_id) values
    -- Midstream: 메모리 제조
    ('005930.KS', 'Samsung Electronics',  'KR', 'memory_semiconductor', ws_id),
    ('000660.KS', 'SK Hynix',             'KR', 'memory_semiconductor', ws_id),
    ('MU',        'Micron Technology',    'US', 'memory_semiconductor', ws_id),
    -- Midstream: Foundry
    ('TSM',       'TSMC',                 'TW', 'memory_semiconductor', ws_id),
    -- Downstream: 팹리스 / GPU / CPU
    ('NVDA',      'NVIDIA',               'US', 'memory_semiconductor', ws_id),
    ('AMD',       'AMD',                  'US', 'memory_semiconductor', ws_id),
    ('INTC',      'Intel',                'US', 'memory_semiconductor', ws_id),
    -- Upstream: 반도체 장비
    ('ASML',      'ASML Holding',         'NL', 'memory_semiconductor', ws_id),
    ('AMAT',      'Applied Materials',    'US', 'memory_semiconductor', ws_id),
    ('LRCX',      'Lam Research',         'US', 'memory_semiconductor', ws_id),
    -- Downstream: 모바일 OEM / 팹리스
    ('AAPL',      'Apple',                'US', 'memory_semiconductor', ws_id),
    ('QCOM',      'Qualcomm',             'US', 'memory_semiconductor', ws_id),
    ('2454.TW',   'MediaTek',             'TW', 'memory_semiconductor', ws_id);

  -- 메모리 반도체 supply chain 엣지 24개 (HBM/DRAM/Foundry + 신규 장비/모바일)
  -- HBM: SK Hynix/Samsung/Micron -> NVIDIA/AMD (HBM = AI GPU 필수)
  -- DRAM: Samsung/SK Hynix/Micron -> Intel (서버용)
  -- Foundry: TSMC -> NVIDIA/AMD/Intel (CoWoS / 5nm)
  -- 신규 - Upstream 장비: ASML/AMAT/LRCX -> 메모리/Foundry
  -- 신규 - TSMC -> Apple/Qualcomm/MediaTek (모바일 SoC foundry)
  -- 신규 - 메모리 3사 -> Apple (모바일 LPDDR / NAND)
  insert into public.edges (supplier_id, buyer_id, product_category, lag_quarters, workspace_id)
  select s.id, b.id, e.product_category, e.lag_quarters, ws_id
  from (values
    -- HBM: 메모리 3사 -> NVIDIA/AMD (AI GPU 필수)
    ('000660.KS', 'NVDA',     'HBM',             1),  -- SK Hynix -> NVIDIA HBM3/HBM3E
    ('005930.KS', 'NVDA',     'HBM',             1),  -- Samsung -> NVIDIA HBM
    ('MU',        'NVDA',     'HBM',             1),  -- Micron -> NVIDIA HBM
    ('000660.KS', 'AMD',      'HBM',             1),  -- SK Hynix -> AMD MI300
    ('005930.KS', 'AMD',      'HBM',             1),
    -- DRAM_DDR5: 메모리 3사 -> Intel (서버용)
    ('000660.KS', 'INTC',     'DRAM_DDR5',       1),
    ('005930.KS', 'INTC',     'DRAM_DDR5',       1),
    ('MU',        'INTC',     'DRAM_DDR5',       1),
    -- FOUNDRY: TSMC -> 기존 팹리스
    ('TSM',       'NVDA',     'FOUNDRY_COWOS',   2),  -- TSMC CoWoS 패키징
    ('TSM',       'AMD',      'FOUNDRY_COWOS',   2),
    ('TSM',       'INTC',     'FOUNDRY_5NM',     2),  -- Intel도 일부 TSMC 위탁
    -- 신규: 장비 -> 메모리/Foundry (lead time 길어 lag=3-4)
    ('ASML',      '005930.KS', 'EUV_LITHOGRAPHY', 4),  -- ASML EUV -> Samsung HBM 라인
    ('ASML',      '000660.KS', 'EUV_LITHOGRAPHY', 4),  -- ASML EUV -> SK Hynix M16
    ('ASML',      'TSM',       'EUV_LITHOGRAPHY', 4),  -- ASML EUV -> TSMC N3 EUV
    ('AMAT',      '005930.KS', 'SEMI_EQUIPMENT',  3),  -- 증착/식각/CMP
    ('AMAT',      'MU',        'SEMI_EQUIPMENT',  3),
    ('LRCX',      '000660.KS', 'MEMORY_ETCH',     3),  -- 메모리 식각/CVD 특화
    ('LRCX',      'MU',        'MEMORY_ETCH',     3),
    -- 신규: TSMC -> 모바일 SoC 팹리스
    ('TSM',       'AAPL',      'FOUNDRY_3NM',     2),  -- Apple A/M (TSMC N3/N4)
    ('TSM',       'QCOM',      'FOUNDRY_4NM',     2),  -- Snapdragon (TSMC N4)
    ('TSM',       '2454.TW',   'FOUNDRY_4NM',     2),  -- Dimensity (TSMC N4)
    -- 신규: 메모리 3사 -> Apple (모바일 LPDDR / NAND)
    ('005930.KS', 'AAPL',      'MOBILE_DRAM',     1),
    ('000660.KS', 'AAPL',      'MOBILE_DRAM',     1),
    ('MU',        'AAPL',      'MOBILE_DRAM',     1)
  ) as e(supplier_ticker, buyer_ticker, product_category, lag_quarters)
  join public.companies s on s.ticker = e.supplier_ticker
  join public.companies b on b.ticker = e.buyer_ticker
  where s.workspace_id = ws_id and b.workspace_id = ws_id;
end $$;
