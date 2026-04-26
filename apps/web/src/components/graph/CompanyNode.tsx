import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { formatUsd } from '../../lib/format';

export type CompanyNodeData = {
  ticker: string;
  name: string;
  country: string;
  sector: string;
  revenue_usd?: number;
};

export type CompanyNodeType = Node<CompanyNodeData, 'company'>;

const countryFlags: Record<string, string> = {
  KR: '🇰🇷',
  US: '🇺🇸',
  JP: '🇯🇵',
  TW: '🇹🇼',
  CN: '🇨🇳',
};

function CompanyNodeComponent({ data }: NodeProps<CompanyNodeType>) {
  // Scale width based on revenue if available (log scale 100-200px)
  let width = 150;
  if (data.revenue_usd) {
    const logRev = Math.log10(Math.max(data.revenue_usd, 1e6));
    // Map logRev (6 to 12) to 100-200
    width = Math.max(100, Math.min(200, 100 + (logRev - 6) * (100 / 6)));
  }

  return (
    <div 
      className="relative rounded-xl border border-foreground/10 bg-background shadow-sm transition-all hover:shadow-md dark:border-foreground/20"
      style={{ width: `${width}px` }}
    >
      <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-brand-accent" />
      
      <div className="p-3 flex flex-col items-center text-center gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-lg" title={data.country}>{countryFlags[data.country] || '🌐'}</span>
          <span className="font-mono font-bold text-lg tracking-tight text-foreground">
            {data.ticker.split('.')[0]}
          </span>
        </div>
        
        <span className="text-xs text-foreground/70 font-medium truncate w-full px-1">
          {data.name}
        </span>
        
        {data.revenue_usd && (
          <div className="mt-1 px-2 py-0.5 bg-brand-primary/10 text-brand-primary dark:bg-brand-primary/20 dark:text-brand-accent rounded-full text-[10px] font-bold tabular-nums">
            {formatUsd(data.revenue_usd)}
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-brand-accent" />
    </div>
  );
}

export const CompanyNode = memo(CompanyNodeComponent);
