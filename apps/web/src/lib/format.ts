export function formatUsd(value: number | null | undefined): string {
  if (value == null) return '-';
  
  const abs = Math.abs(value);
  if (abs >= 1e9) {
    return `$${(value / 1e9).toFixed(1)}B`;
  }
  if (abs >= 1e6) {
    return `$${(value / 1e6).toFixed(1)}M`;
  }
  if (abs >= 1e3) {
    return `$${(value / 1e3).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
}

export function formatPct(value: number | null | undefined): string {
  if (value == null) return '-';
  return `${(value * 100).toFixed(1)}%`;
}

export function formatTicker(ticker: string): string {
  if (!ticker) return '';
  return ticker.split('.')[0] || '';
}
