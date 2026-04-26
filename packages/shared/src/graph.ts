/**
 * Supply chain graph types
 * React Flow 노드/엣지로 변환되는 도메인 모델
 */

import type { GroundedNumber } from './citations.js';

export type CountryCode = 'KR' | 'US' | 'JP' | 'TW' | 'CN';

export type Sector =
  | 'memory_semiconductor'
  | 'display_oled'
  | 'battery_secondary'
  | 'auto_parts';

export interface Company {
  id: string;
  ticker: string; // '000660.KS', 'MU' 등
  name: string;
  country: CountryCode;
  sector: Sector;
}

/**
 * 분기 표기: 'YYYYQn' 형식 (예: '2024Q3')
 */
export type Quarter = `${number}Q${1 | 2 | 3 | 4}`;

export interface SupplyEdge {
  id: string;
  supplier_id: string;
  buyer_id: string;
  product_category: string; // 'HBM', 'DRAM_DDR5' 등
  lag_quarters: number; // 매출 인식 시차 (분기)
}

export interface EdgeMetric {
  id: string;
  edge_id: string;
  quarter: Quarter;
  price: GroundedNumber | null;
  quantity: GroundedNumber | null;
  revenue: GroundedNumber | null;
  is_imputed: boolean;
  is_hypothesis: boolean;
  confidence_score: number; // 1~100
}

export interface ReconciliationError {
  edge_id: string;
  quarter: Quarter;
  supplier_revenue_usd: number;
  buyer_cost_usd: number;
  gap_pct: number; // (B 매입 - A 매출) / A 매출
  severity: 'low' | 'medium' | 'high';
}

export interface SupplyChainGraph {
  sector: Sector;
  quarter: Quarter;
  as_of_date: string; // ISO date
  companies: Company[];
  edges: SupplyEdge[];
  metrics: EdgeMetric[];
  reconciliation_errors: ReconciliationError[];
}
