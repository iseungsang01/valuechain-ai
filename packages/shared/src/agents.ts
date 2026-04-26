/**
 * Agent streaming event types
 * FastAPI SSE → Next.js EventSource로 전송되는 이벤트 wire format
 */

export type AgentName =
  | 'StructureMapper'
  | 'DataCollector'
  | 'QuantEstimator'
  | 'Evaluator';

export type StreamEventType =
  | 'agent_start' // 에이전트 작업 시작
  | 'thought' // 사고 텍스트 청크
  | 'tool_call' // 외부 도구 호출
  | 'tool_result' // 도구 결과 수신
  | 'graph_update' // 부분 그래프 업데이트
  | 'agent_complete' // 에이전트 작업 완료
  | 'pipeline_complete' // 전체 파이프라인 완료
  | 'error'; // 에러 발생

export interface StreamEventBase {
  event_id: string; // UUID, 클라 dedup용
  run_id: string;
  agent: AgentName;
  type: StreamEventType;
  timestamp: string; // ISO datetime
  /**
   * Raw payload from backend TraceEvent.
   * 백엔드 노드가 emit() 으로 송출한 원본 dict 를 그대로 전달.
   * 강타입 variant 필드(text, tool_name, partial_graph 등)와 병행 제공 →
   * 프론트는 강타입 우선, 폴백으로 payload 표시.
   */
  payload?: Record<string, unknown>;
}

export interface ThoughtEvent extends StreamEventBase {
  type: 'thought';
  text: string;
  citation_ids?: string[];
}

export interface ToolCallEvent extends StreamEventBase {
  type: 'tool_call';
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResultEvent extends StreamEventBase {
  type: 'tool_result';
  tool_name: string;
  result_summary: string;
  citation_ids?: string[];
}

export interface GraphUpdateEvent extends StreamEventBase {
  type: 'graph_update';
  partial_graph: {
    companies?: import('./graph.js').Company[];
    edges?: import('./graph.js').SupplyEdge[];
    metrics?: import('./graph.js').EdgeMetric[];
  };
}

/**
 * 에러 카테고리 - 백엔드 ErrorCategory 와 1:1 일치 (T4.2).
 * 프론트가 분기하여 다른 UI/recovery 액션 제공.
 */
export type ErrorCategory =
  | 'auth' // 401, API key 누락/무효
  | 'rate_limit' // 429
  | 'external_api' // 외부 API 5xx, 네트워크
  | 'hallucination' // LLM citation_id 가공 - 차단됨
  | 'time_isolation' // 백테스트 시점 위반
  | 'validation' // 요청 입력 검증 실패
  | 'internal'; // 그 외 unknown

export interface ErrorEvent extends StreamEventBase {
  type: 'error';
  payload: {
    category: ErrorCategory;
    error_code: string;
    message: string;
    retriable: boolean;
  };
}

export type StreamEvent =
  | ThoughtEvent
  | ToolCallEvent
  | ToolResultEvent
  | GraphUpdateEvent
  | ErrorEvent
  | (StreamEventBase & {
      type: 'agent_start' | 'agent_complete' | 'pipeline_complete';
    });

/**
 * Run 생성 요청/응답
 */
export interface RunCreateRequest {
  sector: import('./graph.js').Sector;
  target_quarter: import('./graph.js').Quarter;
  is_backtest?: boolean;
  as_of_date?: string; // ISO date - 백테스트 시 시간 격리용
}

export interface RunCreateResponse {
  run_id: string;
  stream_url: string; // SSE 엔드포인트 URL
}
