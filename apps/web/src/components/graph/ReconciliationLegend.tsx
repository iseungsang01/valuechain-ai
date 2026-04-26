import { memo } from 'react';

function ReconciliationLegendComponent() {
  return (
    <div className="absolute bottom-4 right-14 bg-background/90 backdrop-blur-sm border border-foreground/10 rounded-lg p-3 shadow-sm text-xs z-10">
      <h4 className="font-bold mb-2 text-foreground/80">Reconciliation Status</h4>
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="w-4 h-1 rounded-full bg-[oklch(0.6_0.15_150)] opacity-70"></div>
          <span>Matched (Gap &lt; 5%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-1 rounded-full bg-[var(--color-conflict-low)] opacity-80"></div>
          <span>Warning (Gap 5-15%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-1 rounded-full bg-[var(--color-conflict-high)] opacity-90 animate-pulse"></div>
          <span>Conflict (Gap &gt; 15%)</span>
        </div>
      </div>
    </div>
  );
}

export const ReconciliationLegend = memo(ReconciliationLegendComponent);
