/**
 * SupplyChainFlow - React Flow 컨테이너.
 *
 * GraphStore (wire format) → React Flow Node[]/Edge[] 변환.
 * 노드 좌표는 SCM 흐름 기반 단순 grid (Phase 1).
 * V2: dagre/elkjs 자동 레이아웃.
 */
'use client';

import { useMemo, useState, useCallback } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  MiniMap,
  type Node,
  type Edge,
} from '@xyflow/react';
import { useGraphStore } from '../../stores/useGraphStore';
import { CompanyNode, type CompanyNodeData } from './CompanyNode';
import { TradeEdge, type TradeEdgeData } from './TradeEdge';
import { ReconciliationLegend } from './ReconciliationLegend';
import { EdgeTooltip } from './EdgeTooltip';
import { edgeKey } from '../../lib/wire-types';

const nodeTypes = { company: CompanyNode };
const edgeTypes = { trade: TradeEdge };

interface HoverState {
  x: number;
  y: number;
  edgeId: string;
}

/** 단순 grid 레이아웃 - 노드 수에 따라 cols=ceil(sqrt(n)) 로 적응형 배치. V2: dagre. */
function gridLayout<T>(items: { id: string; node: T }[]): Array<T & { position: { x: number; y: number } }> {
  const cols = Math.max(1, Math.ceil(Math.sqrt(items.length)));
  return items.map((entry, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    return {
      ...(entry.node as object),
      position: { x: col * 280, y: row * 220 },
    } as T & { position: { x: number; y: number } };
  });
}

export function SupplyChainFlow() {
  const storeNodes = useGraphStore((s) => s.nodes);
  const storeEdges = useGraphStore((s) => s.edges);
  const edgeMetrics = useGraphStore((s) => s.edgeMetrics);
  const reconciliationErrors = useGraphStore((s) => s.reconciliationErrors);

  const [hoveredEdge, setHoveredEdge] = useState<HoverState | null>(null);

  const nodes: Node<CompanyNodeData>[] = useMemo(() => {
    const rawNodes = storeNodes.map((n) => {
      const revenue = edgeMetrics
        .filter((m) => m.supplier_ticker === n.ticker)
        .reduce((sum, m) => sum + (m.revenue_usd ?? 0), 0);

      const node: Node<CompanyNodeData> = {
        id: n.ticker,
        type: 'company',
        position: { x: 0, y: 0 },
        data: {
          ticker: n.ticker,
          name: n.name,
          country: n.country,
          sector: n.sector,
          revenue_usd: revenue > 0 ? revenue : undefined,
        },
      };
      return { id: n.ticker, node };
    });

    return gridLayout(rawNodes);
  }, [storeNodes, edgeMetrics]);

  const edges: Edge<TradeEdgeData>[] = useMemo(() => {
    return storeEdges.map((e) => {
      const metric = edgeMetrics.find(
        (m) =>
          m.supplier_ticker === e.supplier_ticker &&
          m.buyer_ticker === e.buyer_ticker &&
          m.product_category === e.product_category,
      );

      const error = reconciliationErrors.find(
        (err) => err.buyer_ticker === e.buyer_ticker,
      );

      let severity: 'low' | 'medium' | 'high' | undefined;
      if (error) severity = error.severity;
      else if (metric) severity = 'low';

      return {
        id: edgeKey(e.supplier_ticker, e.buyer_ticker, e.product_category),
        source: e.supplier_ticker,
        target: e.buyer_ticker,
        type: 'trade',
        animated: !metric,
        data: {
          product_category: e.product_category,
          revenue_usd: metric?.revenue_usd ?? undefined,
          severity,
          is_active: !metric,
        },
      };
    });
  }, [storeEdges, edgeMetrics, reconciliationErrors]);

  const onEdgeMouseEnter = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      const error = reconciliationErrors.find(
        (err) => err.buyer_ticker === edge.target,
      );
      if (error) {
        setHoveredEdge({
          x: event.clientX,
          y: event.clientY,
          edgeId: edge.id,
        });
      }
    },
    [reconciliationErrors],
  );

  const onEdgeMouseMove = useCallback(
    (event: React.MouseEvent) => {
      setHoveredEdge((prev) =>
        prev ? { ...prev, x: event.clientX, y: event.clientY } : null,
      );
    },
    [],
  );

  const onEdgeMouseLeave = useCallback(() => {
    setHoveredEdge(null);
  }, []);

  const tooltipData = useMemo(() => {
    if (!hoveredEdge) return null;
    const edge = edges.find((e) => e.id === hoveredEdge.edgeId);
    if (!edge) return null;

    const error = reconciliationErrors.find(
      (err) => err.buyer_ticker === edge.target,
    );
    if (!error) return null;

    return {
      x: hoveredEdge.x,
      y: hoveredEdge.y,
      supplier: edge.source,
      buyer: edge.target,
      product: edge.data?.product_category ?? '',
      supplierRevenue: error.cogs_usd ?? undefined,
      buyerCost: error.inflow_usd,
      // ratio = inflow/cogs, gap = ratio - 1 (fraction). formatPct 가 *100 적용.
      gapPct: error.ratio !== null ? error.ratio - 1 : undefined,
      severity: error.severity,
    };
  }, [hoveredEdge, edges, reconciliationErrors]);

  return (
    <div className="h-full w-full relative rounded-lg border border-foreground/10 bg-background/50 overflow-hidden">
      {nodes.length === 0 ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-foreground/50 z-10 pointer-events-none">
          <p className="text-lg font-medium mb-2">토폴로지 미리보기</p>
          <p className="text-sm">13개 기업, 24개 거래 관계</p>
          <p className="text-xs mt-4 opacity-70">
            &quot;분석 시작&quot;을 눌러 시작하세요
          </p>
        </div>
      ) : null}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onEdgeMouseEnter={onEdgeMouseEnter}
        onEdgeMouseMove={onEdgeMouseMove}
        onEdgeMouseLeave={onEdgeMouseLeave}
        fitView
        proOptions={{ hideAttribution: false }}
        className="z-0"
      >
        <Background gap={16} />
        <Controls position="bottom-left" />
        <MiniMap
          position="top-right"
          className="!bg-background !border-foreground/10"
          maskColor="var(--color-background)"
        />
      </ReactFlow>

      {nodes.length > 0 && <ReconciliationLegend />}

      {tooltipData && <EdgeTooltip {...tooltipData} />}
    </div>
  );
}
