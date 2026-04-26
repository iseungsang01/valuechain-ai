/**
 * AgentErrorPanel - SSE error event 의 사용자 친화 UI (T4.2).
 *
 * 백엔드 ErrorClassification.to_payload() → ErrorEvent.payload 형태:
 *   { category, error_code, message, retriable }
 *
 * 카테고리별 분기:
 * - hallucination: 빨강 + "AI 출력 차단" 메시지 + 재시도 버튼 비활성화
 * - rate_limit / external_api: 노랑 + "재시도 가능" 메시지 + 자동 재연결 안내
 * - auth: 주황 + "관리자 문의" 메시지 + 재시도 버튼 비활성화
 * - time_isolation: 파랑 + "데이터 시점 확인" 안내
 * - validation / internal: 회색 + 일반 안내
 */
'use client';

import { useMemo } from 'react';
import type { ErrorCategory } from '@valuechain/shared/agents';

export interface AgentError {
  category: ErrorCategory;
  error_code: string;
  message: string;
  retriable: boolean;
}

interface Props {
  error: AgentError;
  onRetry?: () => void;
  /** 자동 재연결 시도 횟수 (예: 1/3) */
  reconnectAttempt?: number;
  /** 최대 재연결 횟수 */
  maxReconnects?: number;
  onDismiss?: () => void;
}

interface CategoryStyle {
  /** Tailwind border + bg 토큰 (light + dark 자동) */
  surface: string;
  /** 아이콘 색 */
  iconColor: string;
  /** 카테고리 라벨 */
  label: string;
  /** 권장 액션 안내 */
  guidance: string;
  /** SVG 아이콘 path - 단일 stroke 형태로 통일 */
  iconPath: ReadonlyArray<string>;
}

const CATEGORY_STYLES: Record<ErrorCategory, CategoryStyle> = {
  hallucination: {
    surface: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
    iconColor: 'text-red-500',
    label: 'AI 환각 차단',
    guidance:
      'AI가 출처가 없는 수치를 생성하려고 시도했습니다. 신뢰성을 위해 결과가 거부되었습니다.',
    iconPath: [
      'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z',
      'M12 9v4',
      'M12 17h.01',
    ],
  },
  rate_limit: {
    surface:
      'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    iconColor: 'text-amber-500',
    label: '호출 한도 도달',
    guidance: '외부 API 한도에 도달했습니다. 잠시 후 자동으로 재시도됩니다.',
    iconPath: ['M12 8v4l3 3', 'M12 22a10 10 0 100-20 10 10 0 000 20z'],
  },
  external_api: {
    surface:
      'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    iconColor: 'text-amber-500',
    label: '외부 데이터 일시 오류',
    guidance: '데이터 소스 응답이 늦거나 일시 오류 상태입니다. 재시도가 가능합니다.',
    iconPath: [
      'M21 12a9 9 0 11-9-9 9 9 0 019 9z',
      'M3.6 9h16.8',
      'M3.6 15h16.8',
    ],
  },
  auth: {
    surface:
      'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300',
    iconColor: 'text-orange-500',
    label: '인증 실패',
    guidance:
      '데이터 소스 인증에 실패했습니다. 관리자가 API 키를 갱신해야 합니다.',
    iconPath: [
      'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
      'M9 12l2 2 4-4',
    ],
  },
  time_isolation: {
    surface:
      'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300',
    iconColor: 'text-sky-500',
    label: '백테스트 시점 위반',
    guidance:
      '분석 시점 이후 데이터가 사용되었습니다. 출처 시점을 확인해주세요.',
    iconPath: ['M12 6v6l4 2', 'M21 12a9 9 0 11-9-9 9 9 0 019 9z'],
  },
  validation: {
    surface:
      'border-foreground/20 bg-foreground/5 text-foreground/80',
    iconColor: 'text-foreground/60',
    label: '입력값 오류',
    guidance: '요청 입력을 확인하고 다시 시도해주세요.',
    iconPath: [
      'M12 9v4',
      'M12 17h.01',
      'M12 22a10 10 0 100-20 10 10 0 000 20z',
    ],
  },
  internal: {
    surface:
      'border-foreground/20 bg-foreground/5 text-foreground/80',
    iconColor: 'text-foreground/60',
    label: '시스템 오류',
    guidance: '예상치 못한 오류입니다. 문제가 지속되면 관리자에게 문의해주세요.',
    iconPath: [
      'M12 9v4',
      'M12 17h.01',
      'M21 12a9 9 0 11-9-9 9 9 0 019 9z',
    ],
  },
};

function StatusIcon({ paths, className }: { paths: ReadonlyArray<string>; className: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

export function AgentErrorPanel({
  error,
  onRetry,
  reconnectAttempt,
  maxReconnects,
  onDismiss,
}: Props) {
  const style = useMemo<CategoryStyle>(
    () => CATEGORY_STYLES[error.category] ?? CATEGORY_STYLES.internal,
    [error.category],
  );

  const showReconnecting =
    error.retriable &&
    reconnectAttempt !== undefined &&
    maxReconnects !== undefined &&
    reconnectAttempt > 0;

  return (
    <div
      role="alert"
      data-testid="agent-error-panel"
      data-error-category={error.category}
      data-error-code={error.error_code}
      data-retriable={error.retriable}
      className={`flex flex-col gap-3 rounded-lg border px-4 py-3 text-sm ${style.surface}`}
    >
      <div className="flex items-start gap-3">
        <StatusIcon paths={style.iconPath} className={`mt-0.5 shrink-0 ${style.iconColor}`} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 font-bold">
            <span>{style.label}</span>
            <span
              className="font-mono text-[10px] tracking-tight opacity-60"
              title={error.error_code}
            >
              {error.error_code}
            </span>
          </div>

          <p
            className="mt-1 text-xs opacity-90"
            data-testid="agent-error-message"
          >
            {error.message}
          </p>

          <p className="mt-1 text-[11px] opacity-70">{style.guidance}</p>
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="ml-2 shrink-0 opacity-60 transition-opacity hover:opacity-100"
            aria-label="에러 메시지 닫기"
          >
            ✕
          </button>
        )}
      </div>

      {showReconnecting && (
        <div
          className="flex items-center gap-2 text-[11px] opacity-80"
          data-testid="agent-error-reconnecting"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-50" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
          </span>
          자동 재연결 중... ({reconnectAttempt}/{maxReconnects})
        </div>
      )}

      {error.retriable && onRetry && !showReconnecting && (
        <button
          type="button"
          onClick={onRetry}
          data-testid="agent-error-retry"
          className="self-start rounded border border-current/30 px-3 py-1 text-xs font-bold transition-opacity hover:opacity-80"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}
