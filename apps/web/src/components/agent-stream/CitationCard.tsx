import { memo, useState } from 'react';

interface CitationCardProps {
  id: string;
  url?: string;
  type?: string;
  date?: string;
  snippet?: string;
}

function CitationCardComponent({ id, url, type = 'DART', date, snippet }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  
  const displaySnippet = snippet || 'No snippet available.';
  const isLong = displaySnippet.length > 100;
  
  return (
    <div className="mt-2 text-xs border border-foreground/10 rounded bg-foreground/5 overflow-hidden">
      <div className="flex items-center justify-between px-2 py-1.5 bg-foreground/5 border-b border-foreground/5">
        <div className="flex items-center gap-2">
          <span className="px-1.5 py-0.5 rounded-sm bg-brand-primary/20 text-brand-primary dark:text-brand-accent font-mono text-[10px] font-bold">
            {type}
          </span>
          <span className="font-mono text-foreground/60">{id}</span>
        </div>
        {date && <span className="text-foreground/50">{date}</span>}
      </div>
      
      <div 
        className="p-2 cursor-pointer hover:bg-foreground/5 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <p className={`text-foreground/80 ${!expanded && isLong ? 'line-clamp-2' : ''}`}>
          {displaySnippet}
        </p>
        {!expanded && isLong && (
          <span className="text-brand-primary dark:text-brand-accent text-[10px] mt-1 inline-block font-medium">
            Read more...
          </span>
        )}
      </div>
      
      {url && (
        <div className="px-2 py-1.5 border-t border-foreground/5 bg-background/50">
          <a 
            href={url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-brand-primary dark:text-brand-accent hover:underline flex items-center gap-1"
          >
            <span>Source Document</span>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
        </div>
      )}
    </div>
  );
}

export const CitationCard = memo(CitationCardComponent);
