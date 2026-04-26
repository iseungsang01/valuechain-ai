import { memo, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { StreamEvent } from '../../lib/sse-types';
import { CitationCard } from './CitationCard';

interface AgentColumnProps {
  name: string;
  events: StreamEvent[];
  isActive: boolean;
  isComplete: boolean;
  hasError: boolean;
}

function AgentColumnComponent({ name, events, isActive, isComplete, hasError }: AgentColumnProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  let statusColor = 'bg-foreground/10 text-foreground/50';
  let statusText = '대기 중';
  
  if (hasError) {
    statusColor = 'bg-red-500/20 text-red-500';
    statusText = '오류';
  } else if (isComplete) {
    statusColor = 'bg-green-500/20 text-green-500';
    statusText = '완료 ✓';
  } else if (isActive) {
    statusColor = 'bg-brand-primary/20 text-brand-primary dark:text-brand-accent animate-pulse';
    statusText = '실행 중...';
  }

  return (
    <div className="flex flex-col h-full border-r border-foreground/10 last:border-r-0 bg-background/30">
      <div className="p-3 border-b border-foreground/10 bg-background/50 sticky top-0 z-10">
        <h3 className="font-bold text-sm mb-1 truncate" title={name}>{name}</h3>
        <div className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${statusColor}`}>
          {statusText}
        </div>
      </div>
      
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-3 scroll-smooth"
      >
        <AnimatePresence initial={false}>
          {events.map((event) => {
            if (event.type === 'thought') {
              return (
                <motion.div
                  key={event.event_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-background border border-foreground/10 rounded-lg p-2.5 shadow-sm text-sm"
                >
                  <p className="text-foreground/80 leading-relaxed">{event.text}</p>
                  
                  {event.citation_ids && event.citation_ids.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {event.citation_ids.map(id => (
                        <CitationCard key={id} id={id} />
                      ))}
                    </div>
                  )}
                </motion.div>
              );
            }
            
            if (event.type === 'tool_call') {
              return (
                <motion.div
                  key={event.event_id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="bg-foreground/5 border border-foreground/10 rounded-lg p-2 text-xs font-mono"
                >
                  <div className="text-foreground/50 mb-1">🔧 도구 호출</div>
                  <div className="text-brand-primary dark:text-brand-accent font-bold">
                    {event.tool_name}
                  </div>
                </motion.div>
              );
            }
            
            if (event.type === 'error') {
              // T4.2: ErrorEvent 페이로드 = { category, error_code, message, retriable }
              const errorCode = event.payload?.error_code ?? 'UNKNOWN';
              const errorMsg = event.payload?.message ?? '알 수 없는 오류';
              return (
                <motion.div
                  key={event.event_id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="bg-red-500/10 border border-red-500/20 rounded-lg p-2.5 text-sm text-red-500"
                >
                  <div className="font-bold mb-1">오류: {errorCode}</div>
                  <p>{errorMsg}</p>
                </motion.div>
              );
            }
            
            return null;
          })}
        </AnimatePresence>
        
        {events.length === 0 && !isActive && !isComplete && (
          <div className="text-center text-foreground/30 text-xs mt-10">
            Waiting for input...
          </div>
        )}
      </div>
    </div>
  );
}

export const AgentColumn = memo(AgentColumnComponent);
