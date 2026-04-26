import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps, type Edge } from '@xyflow/react';
import { formatUsd } from '../../lib/format';

export type TradeEdgeData = {
  product_category: string;
  revenue_usd?: number;
  severity?: 'low' | 'medium' | 'high';
  is_active?: boolean;
};

export type TradeEdgeType = Edge<TradeEdgeData, 'trade'>;

function TradeEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<TradeEdgeType>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Stroke width based on revenue
  let strokeWidth = 1.5;
  if (data?.revenue_usd) {
    const logRev = Math.log10(Math.max(data.revenue_usd, 1e6));
    strokeWidth = Math.max(1.5, Math.min(6, 1.5 + (logRev - 6) * 0.5));
  }

  // Color based on severity
  let strokeColor = 'var(--color-foreground)';
  let strokeOpacity = 0.3;
  
  if (data?.severity === 'high') {
    strokeColor = 'var(--color-conflict-high)';
    strokeOpacity = 0.9;
  } else if (data?.severity === 'medium') {
    strokeColor = 'var(--color-conflict-low)';
    strokeOpacity = 0.8;
  } else if (data?.severity === 'low') {
    strokeColor = 'oklch(0.6 0.15 150)'; // Greenish
    strokeOpacity = 0.7;
  }

  const isConflict = data?.severity === 'high' || data?.severity === 'medium';

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          strokeWidth,
          stroke: strokeColor,
          strokeOpacity,
        }}
        className={isConflict ? 'edge-conflict' : (data?.is_active ? 'animate-pulse' : '')}
      />
      
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          <div className="flex flex-col items-center bg-background/90 backdrop-blur-sm border border-foreground/10 rounded px-1.5 py-0.5 text-[10px] shadow-sm">
            <span className="font-medium text-foreground/80">{data?.product_category}</span>
            {data?.revenue_usd && (
              <span className="font-bold tabular-nums text-brand-primary dark:text-brand-accent">
                {formatUsd(data.revenue_usd)}
              </span>
            )}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const TradeEdge = memo(TradeEdgeComponent);
