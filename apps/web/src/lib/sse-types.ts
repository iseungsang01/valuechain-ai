import type { StreamEvent, StreamEventBase } from '@valuechain/shared/agents';

export type { StreamEvent, StreamEventBase };

export function isStreamEvent(x: unknown): x is StreamEvent {
  if (!x || typeof x !== 'object') return false;
  const obj = x as Record<string, unknown>;
  return (
    typeof obj.event_id === 'string' &&
    typeof obj.run_id === 'string' &&
    typeof obj.agent === 'string' &&
    typeof obj.type === 'string' &&
    typeof obj.timestamp === 'string'
  );
}
