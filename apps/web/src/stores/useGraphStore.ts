/**
 * GraphStore - SSE graph_update 이벤트로 누적되는 supply chain 상태.
 *
 * 백엔드 wire format(ticker-based)을 그대로 보관 → React Flow 변환은 SupplyChainFlow 에서.
 * Upsert by composite key (supplier+buyer+product) 로 중복 없이 누적.
 */

import { create } from 'zustand';
import type {
  WireTopologyNode,
  WireTopologyEdge,
  WireEdgeMetric,
  WireReconciliationError,
  WirePartialGraph,
} from '../lib/wire-types';
import { edgeKey } from '../lib/wire-types';

interface GraphState {
  nodes: WireTopologyNode[];
  edges: WireTopologyEdge[];
  edgeMetrics: WireEdgeMetric[];
  reconciliationErrors: WireReconciliationError[];
  ingestUpdate: (partial: WirePartialGraph) => void;
  reset: () => void;
}

function upsertBy<T>(list: T[], item: T, keyOf: (x: T) => string): T[] {
  const key = keyOf(item);
  const idx = list.findIndex((x) => keyOf(x) === key);
  if (idx >= 0) {
    const next = list.slice();
    next[idx] = { ...next[idx], ...item };
    return next;
  }
  return [...list, item];
}

export const useGraphStore = create<GraphState>((set) => ({
  nodes: [],
  edges: [],
  edgeMetrics: [],
  reconciliationErrors: [],

  ingestUpdate: (partial) =>
    set((state) => {
      let { nodes, edges, edgeMetrics, reconciliationErrors } = state;

      if (partial.nodes && partial.nodes.length > 0) {
        for (const n of partial.nodes) {
          nodes = upsertBy(nodes, n, (x) => x.ticker);
        }
      }

      if (partial.edges && partial.edges.length > 0) {
        for (const e of partial.edges) {
          edges = upsertBy(edges, e, (x) =>
            edgeKey(x.supplier_ticker, x.buyer_ticker, x.product_category),
          );
        }
      }

      if (partial.edge_metrics && partial.edge_metrics.length > 0) {
        for (const m of partial.edge_metrics) {
          edgeMetrics = upsertBy(edgeMetrics, m, (x) =>
            edgeKey(x.supplier_ticker, x.buyer_ticker, x.product_category),
          );
        }
      }

      if (partial.reconciliation_errors && partial.reconciliation_errors.length > 0) {
        for (const err of partial.reconciliation_errors) {
          reconciliationErrors = upsertBy(
            reconciliationErrors,
            err,
            (x) => `${x.buyer_ticker}|${x.error_type}`,
          );
        }
      }

      return { nodes, edges, edgeMetrics, reconciliationErrors };
    }),

  reset: () =>
    set({ nodes: [], edges: [], edgeMetrics: [], reconciliationErrors: [] }),
}));
