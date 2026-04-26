/**
 * SSE wire format types - 백엔드가 graph_update 페이로드로 보내는 RAW 모양.
 *
 * 주의: packages/shared/src/graph.ts 의 도메인 타입(Company, SupplyEdge, EdgeMetric)은
 * UUID 기반(supplier_id 등) DB-side 표현이지만, 실제 SSE wire 는 ticker 기반.
 *
 * 따라서 프론트는 wire 타입을 직접 사용하고, 도메인 타입은 향후 DB 직결 시에만 활용.
 */

import type { CountryCode } from '@valuechain/shared/graph';

/** topology.nodes 항목 - apps/api/app/agents/topology/memory_semi.py TopologyNode 와 1:1 */
export interface WireTopologyNode {
  ticker: string;
  name: string;
  country: CountryCode;
  sector: string;
}

/** topology.edges 항목 - TopologyEdge 와 1:1 */
export interface WireTopologyEdge {
  supplier_ticker: string;
  buyer_ticker: string;
  product_category: string;
  lag_quarters: number;
}

/** quantified.edge_metrics 항목 - quant_estimator.py 가 만드는 dict 모양 */
export interface WireEdgeMetric {
  edge_id?: string;
  metric_id?: string;
  supplier_ticker: string;
  buyer_ticker: string;
  product_category: string;
  quarter: string;
  revenue_usd: number | null;
  product_share?: number;
  n_buyers_for_product?: number;
  is_imputed: boolean;
  is_hypothesis: boolean;
  confidence_score: number;
  citation_ids: string[];
}

/** reconciliation_errors 항목 - reconciliation.py 가 만드는 dict 모양 */
export interface WireReconciliationError {
  buyer_ticker: string;
  error_type: 'inflow_exceeds_cogs' | 'missing_buyer_cogs';
  inflow_usd: number;
  cogs_usd: number | null;
  ratio: number | null;
  tolerance?: number;
  severity: 'low' | 'medium' | 'high';
  message: string;
}

/** graph_update 이벤트의 partial_graph 페이로드 - stream.py 가 합성 */
export interface WirePartialGraph {
  nodes?: WireTopologyNode[];
  edges?: WireTopologyEdge[];
  edge_metrics?: WireEdgeMetric[];
  reconciliation_errors?: WireReconciliationError[];
}

/** Edge 식별자 헬퍼 - 모든 곳에서 일관된 키 생성 */
export function edgeKey(supplier: string, buyer: string, product: string): string {
  return `${supplier}->${buyer}|${product}`;
}
