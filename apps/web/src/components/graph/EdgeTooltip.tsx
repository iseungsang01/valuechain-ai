import { memo } from 'react';
import { formatUsd, formatPct } from '../../lib/format';

interface EdgeTooltipProps {
  x: number;
  y: number;
  supplier: string;
  buyer: string;
  product: string;
  supplierRevenue?: number;
  buyerCost?: number;
  gapPct?: number;
  severity?: 'low' | 'medium' | 'high';
}

function EdgeTooltipComponent({
  x,
  y,
  supplier,
  buyer,
  product,
  supplierRevenue,
  buyerCost,
  gapPct,
  severity
}: EdgeTooltipProps) {
  if (!severity) return null;

  let severityColor = 'text-green-500';
  if (severity === 'high') severityColor = 'text-[var(--color-conflict-high)]';
  else if (severity === 'medium') severityColor = 'text-[var(--color-conflict-low)]';

  return (
    <div 
      className="absolute z-50 bg-background border border-foreground/20 shadow-xl rounded-lg p-3 text-sm w-64 pointer-events-none"
      style={{ left: x + 15, top: y + 15 }}
    >
      <div className="flex justify-between items-center mb-2 pb-2 border-b border-foreground/10">
        <div className="font-mono font-bold">{supplier} → {buyer}</div>
        <div className="text-xs bg-foreground/5 px-1.5 py-0.5 rounded">{product}</div>
      </div>
      
      <div className="space-y-1.5">
        <div className="flex justify-between">
          <span className="text-foreground/60">Supplier Revenue:</span>
          <span className="font-mono">{formatUsd(supplierRevenue)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-foreground/60">Buyer Cost:</span>
          <span className="font-mono">{formatUsd(buyerCost)}</span>
        </div>
        
        <div className="flex justify-between items-center pt-1 mt-1 border-t border-foreground/5">
          <span className="text-foreground/60">Gap:</span>
          <span className={`font-mono font-bold ${severityColor}`}>
            {formatPct(gapPct)}
          </span>
        </div>
      </div>
    </div>
  );
}

export const EdgeTooltip = memo(EdgeTooltipComponent);
