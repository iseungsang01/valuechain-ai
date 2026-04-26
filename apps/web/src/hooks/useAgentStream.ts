/**
 * useAgentStream - POST /api/runs → SSE stream → 에이전트 사고 + graph 업데이트.
 *
 * @microsoft/fetch-event-source 사용 - POST 후 GET SSE 표준 (browser EventSource 는 GET 만).
 * AbortController 로 cleanup 안전.
 *
 * T4.2: 네트워크 끊김 자동 재연결 (최대 3회, exponential backoff).
 *  - 백엔드가 retriable=false 인 error event 송출 → 재연결 중단
 *  - 백엔드가 pipeline_complete 송출 → 재연결 중단
 *  - 사용자가 stop() 호출 → 재연결 중단
 *  - 네트워크 onerror 또는 onclose 발생 → 재연결 시도
 */

import { useState, useCallback, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useGraphStore } from '../stores/useGraphStore';
import { isStreamEvent, type StreamEvent } from '../lib/sse-types';
import type { ErrorCategory } from '@valuechain/shared/agents';
import type { WirePartialGraph } from '../lib/wire-types';
import type { AgentError } from '../components/error/AgentErrorPanel';

export type StreamStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'reconnecting' // T4.2: SSE 끊김 후 자동 재연결 시도 중
  | 'complete'
  | 'error';

interface RunCreateResponse {
  run_id: string;
  stream_url: string;
}

const MAX_RECONNECT_ATTEMPTS = 3;
/** 재연결 시도 간격 (ms) - exponential 1s → 2s → 4s */
const RECONNECT_DELAY_MS = (attempt: number): number => 1000 * 2 ** (attempt - 1);

function isPartialGraph(value: unknown): value is WirePartialGraph {
  if (!value || typeof value !== 'object') return false;
  return true;
}

/** SSE error event payload → AgentError. 잘못된 형식이면 null. */
function extractAgentError(payload: unknown): AgentError | null {
  if (!payload || typeof payload !== 'object') return null;
  const obj = payload as Record<string, unknown>;

  const allowedCategories: ReadonlySet<ErrorCategory> = new Set([
    'auth',
    'rate_limit',
    'external_api',
    'hallucination',
    'time_isolation',
    'validation',
    'internal',
  ]);

  const category =
    typeof obj.category === 'string' &&
    allowedCategories.has(obj.category as ErrorCategory)
      ? (obj.category as ErrorCategory)
      : 'internal';

  const error_code =
    typeof obj.error_code === 'string' ? obj.error_code : 'INTERNAL_ERROR';
  const message =
    typeof obj.message === 'string' ? obj.message : '알 수 없는 오류';
  const retriable = typeof obj.retriable === 'boolean' ? obj.retriable : false;

  return { category, error_code, message, retriable };
}

interface RunArgs {
  sector: string;
  targetQuarter: string;
}

export function useAgentStream() {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [runId, setRunId] = useState<string | null>(null);
  /** 단순 문자열 에러 - V2 호환 (구 컴포넌트가 사용) */
  const [error, setError] = useState<string | null>(null);
  /** T4.2: 분류된 에러 객체 - AgentErrorPanel 이 사용 */
  const [agentError, setAgentError] = useState<AgentError | null>(null);
  /** T4.2: 재연결 시도 횟수 - UI 안내용 (1..MAX_RECONNECT_ATTEMPTS) */
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const ingestUpdate = useGraphStore((state) => state.ingestUpdate);
  const resetGraph = useGraphStore((state) => state.reset);

  const abortControllerRef = useRef<AbortController | null>(null);
  /** 사용자가 명시적으로 stop() 한 경우 재연결 막기 위함 */
  const userStoppedRef = useRef(false);
  /** 백엔드가 retriable=false error / pipeline_complete 송출 시 막기 위함 */
  const terminatedRef = useRef(false);
  const lastRunArgsRef = useRef<RunArgs | null>(null);

  const reset = useCallback(() => {
    setEvents([]);
    setError(null);
    setAgentError(null);
    setReconnectAttempt(0);
    resetGraph();
    terminatedRef.current = false;
  }, [resetGraph]);

  /**
   * 단일 SSE 연결 시도. onerror 발생 + 재연결 가능 시 재귀로 재시도.
   * 호출자(start)가 try 외부에서 lastRunArgsRef 를 세팅한 뒤 호출.
   */
  const connectStream = useCallback(
    async (newRunId: string, baseUrl: string, streamUrl: string): Promise<void> => {
      // 이전 시도 중이라면 중단
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      let receivedAny = false;

      try {
        await fetchEventSource(`${baseUrl}${streamUrl}`, {
          method: 'GET',
          signal: abortControllerRef.current.signal,
          // 재연결 성공 시 한 번 진입 - 정상 streaming 으로 간주
          onopen: async (response) => {
            if (!response.ok) {
              throw new Error(
                `SSE connect failed: ${response.status} ${response.statusText}`,
              );
            }
            setStatus('streaming');
            setReconnectAttempt(0);
          },
          onmessage(msg) {
            if (msg.event === 'ping') return;
            receivedAny = true;

            try {
              const parsed: unknown = JSON.parse(msg.data);
              if (!isStreamEvent(parsed)) return;

              setEvents((prev) => [...prev, parsed]);

              if (parsed.type === 'graph_update') {
                const payload = parsed.payload;
                if (
                  payload &&
                  typeof payload === 'object' &&
                  'partial_graph' in payload
                ) {
                  const partial = (payload as { partial_graph: unknown })
                    .partial_graph;
                  if (isPartialGraph(partial)) {
                    ingestUpdate(partial);
                  }
                }
              }

              if (parsed.type === 'pipeline_complete') {
                terminatedRef.current = true;
                setStatus('complete');
              }

              if (parsed.type === 'error') {
                const ae = extractAgentError(parsed.payload);
                if (ae) {
                  setAgentError(ae);
                  setError(ae.message);
                  if (!ae.retriable) {
                    // 재시도해도 같은 결과 - 종료
                    terminatedRef.current = true;
                    setStatus('error');
                  }
                  // retriable=true 인 경우, 백엔드가 알아서 보낸 마지막 에러일 수 있음.
                  // 연결이 닫힌 뒤 onclose 에서 재연결 분기됨.
                } else {
                  setStatus('error');
                  setError('알 수 없는 오류 (페이로드 형식 불일치)');
                  terminatedRef.current = true;
                }
              }
            } catch (err) {
              // SSE chunk 파싱 실패는 logging 으로만 기록
              // eslint-disable-next-line no-console
              console.error('Failed to parse SSE message', err);
            }
          },
          onerror(err) {
            // 라이브러리가 throw 하면 retry 멈춤 - 우리는 직접 재연결 관리
            // eslint-disable-next-line no-console
            console.error('SSE error:', err);
            throw err;
          },
          onclose() {
            // 정상 close 시점은 onmessage 에서 terminatedRef 가 true 가 됨.
            // 그렇지 않으면 onerror 처럼 재연결 후보.
          },
        });
      } catch (err) {
        // 사용자가 abort 하거나 정상 종료된 경우 throw 안 함.
        if (userStoppedRef.current || terminatedRef.current) {
          return;
        }

        // 재연결 시도 가능 여부 평가
        if (reconnectAttempt < MAX_RECONNECT_ATTEMPTS) {
          const nextAttempt = reconnectAttempt + 1;
          setReconnectAttempt(nextAttempt);
          setStatus('reconnecting');
          // 첫 청크도 못 받았다면 더 빨리 재시도, 받았다면 표준 backoff
          const delay = receivedAny ? RECONNECT_DELAY_MS(nextAttempt) : 500;
          await new Promise<void>((resolve) => {
            setTimeout(resolve, delay);
          });
          if (userStoppedRef.current || terminatedRef.current) return;
          await connectStream(newRunId, baseUrl, streamUrl);
          return;
        }

        // 재연결 한도 초과 - 사용자에게 명시적 에러 노출
        setStatus('error');
        const message = err instanceof Error ? err.message : '연결 오류';
        setError(`재연결 ${MAX_RECONNECT_ATTEMPTS}회 모두 실패: ${message}`);
        setAgentError({
          category: 'external_api',
          error_code: 'SSE_RECONNECT_EXHAUSTED',
          message: `네트워크 연결이 ${MAX_RECONNECT_ATTEMPTS}회 재시도 후에도 복구되지 않았습니다.`,
          retriable: true,
        });
      }
    },
    [ingestUpdate, reconnectAttempt],
  );

  const start = useCallback(
    async (sector: string, targetQuarter: string) => {
      try {
        // 이전 상태 초기화
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }
        userStoppedRef.current = false;
        terminatedRef.current = false;

        setStatus('connecting');
        setEvents([]);
        setError(null);
        setAgentError(null);
        setReconnectAttempt(0);
        resetGraph();

        const baseUrl =
          process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

        const res = await fetch(`${baseUrl}/api/runs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sector, target_quarter: targetQuarter }),
        });

        if (!res.ok) {
          // POST /api/runs 가 우리 분류된 페이로드 반환 → 그대로 사용
          let body: unknown = null;
          try {
            body = await res.json();
          } catch {
            // ignore
          }
          const ae = extractAgentError(body);
          if (ae) {
            setAgentError(ae);
            setError(ae.message);
          } else {
            setError(`Failed to start run: ${res.status} ${res.statusText}`);
          }
          setStatus('error');
          return;
        }

        const data: RunCreateResponse = await res.json();
        const newRunId = data.run_id;
        const streamUrl =
          data.stream_url || `/api/runs/${newRunId}/stream`;

        setRunId(newRunId);
        lastRunArgsRef.current = { sector, targetQuarter };

        await connectStream(newRunId, baseUrl, streamUrl);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Start run error:', err);
        setStatus('error');
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    },
    [connectStream, resetGraph],
  );

  const stop = useCallback(() => {
    userStoppedRef.current = true;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setStatus('idle');
    setReconnectAttempt(0);
  }, []);

  const retry = useCallback(() => {
    if (!lastRunArgsRef.current) return;
    const { sector, targetQuarter } = lastRunArgsRef.current;
    void start(sector, targetQuarter);
  }, [start]);

  return {
    events,
    status,
    runId,
    start,
    stop,
    retry,
    error,
    agentError,
    reconnectAttempt,
    maxReconnects: MAX_RECONNECT_ATTEMPTS,
    reset,
  };
}
