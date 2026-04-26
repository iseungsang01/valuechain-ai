import { memo, useMemo } from 'react';
import { AgentColumn } from './AgentColumn';
import type { StreamEvent } from '../../lib/sse-types';

interface ThoughtPanelProps {
  events: StreamEvent[];
  status: string;
}

const AGENTS = ['StructureMapper', 'DataCollector', 'QuantEstimator', 'Evaluator'];

function ThoughtPanelComponent({ events, status }: ThoughtPanelProps) {
  // Group events by agent
  const eventsByAgent = useMemo(() => {
    const grouped: Record<string, StreamEvent[]> = {};
    AGENTS.forEach(a => grouped[a] = []);
    
    events.forEach(e => {
      if (e.agent && grouped[e.agent]) {
        grouped[e.agent]!.push(e);
      }
    });
    
    return grouped;
  }, [events]);

  // Determine agent status
  const agentStatus = useMemo(() => {
    const statusMap: Record<string, { isActive: boolean; isComplete: boolean; hasError: boolean }> = {};
    
    AGENTS.forEach(agent => {
      const agentEvents = eventsByAgent[agent] || [];
      const hasStart = agentEvents.some(e => e.type === 'agent_start');
      const hasComplete = agentEvents.some(e => e.type === 'agent_complete');
      const hasError = agentEvents.some(e => e.type === 'error');
      
      statusMap[agent] = {
        isActive: hasStart && !hasComplete && !hasError && status !== 'error',
        isComplete: hasComplete,
        hasError: hasError
      };
    });
    
    return statusMap;
  }, [eventsByAgent, status]);

  return (
    <div className="h-full w-full flex flex-col rounded-lg border border-foreground/10 bg-background/50 overflow-hidden">
      <div className="px-4 py-3 border-b border-foreground/10 bg-background/80 flex justify-between items-center">
        <h2 className="font-bold flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-brand-primary dark:text-brand-accent">
            <polyline points="4 17 10 11 4 5"></polyline>
            <line x1="12" y1="19" x2="20" y2="19"></line>
          </svg>
          Agent Thoughts
        </h2>
        
        {status === 'streaming' && (
          <div className="flex items-center gap-2 text-xs font-medium text-brand-primary dark:text-brand-accent">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-primary dark:bg-brand-accent opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-primary dark:bg-brand-accent"></span>
            </span>
            Live Stream
          </div>
        )}
      </div>
      
      <div className="flex-1 grid grid-cols-4 overflow-hidden">
        {AGENTS.map(agent => (
          <AgentColumn 
            key={agent}
            name={agent}
            events={eventsByAgent[agent] || []}
            isActive={agentStatus[agent]?.isActive || false}
            isComplete={agentStatus[agent]?.isComplete || false}
            hasError={agentStatus[agent]?.hasError || false}
          />
        ))}
      </div>
    </div>
  );
}

export const ThoughtPanel = memo(ThoughtPanelComponent);
