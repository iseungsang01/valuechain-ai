/**
 * ErrorBoundary - React 렌더링 트리에서 발생한 예외를 캐치 (T4.2).
 *
 * 캐치 범위:
 * - 자식 컴포넌트의 render / lifecycle / constructor 예외
 * - 비-async 코드의 throw
 *
 * 미캐치 범위:
 * - 이벤트 핸들러 예외 (별도 try/catch 필요)
 * - async / Promise reject (별도 처리)
 * - Server-side 렌더링 예외 (Next.js App Router 의 error.tsx 사용)
 *
 * 사용:
 * ```tsx
 * <ErrorBoundary fallback={<AgentErrorPanel />}>
 *   <Dashboard />
 * </ErrorBoundary>
 * ```
 */
'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  /** 폴백 UI - ReactNode 또는 (error, reset) → ReactNode 함수 */
  fallback?:
    | ReactNode
    | ((error: Error, reset: () => void) => ReactNode);
  /** 에러 발생 시 호출 - 운영 로깅 / Sentry 연동 등 */
  onError?: (error: Error, info: ErrorInfo) => void;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // 개발 콘솔 - 운영에선 Sentry 등으로 교체 (V2)
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] caught render error:', error, info);
    this.props.onError?.(error, info);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (error) {
      const { fallback } = this.props;
      if (typeof fallback === 'function') {
        return fallback(error, this.reset);
      }
      if (fallback !== undefined) {
        return fallback;
      }
      // 기본 폴백 - 미니멀 UI
      return (
        <div
          role="alert"
          data-testid="error-boundary-fallback"
          className="flex h-full w-full flex-col items-center justify-center gap-4 rounded-lg border border-red-500/20 bg-red-500/5 p-8 text-center"
        >
          <div className="text-2xl font-bold text-red-500">
            예상치 못한 오류
          </div>
          <p className="max-w-md text-sm text-foreground/70">
            화면을 그리는 중 문제가 발생했습니다. 다시 시도해주세요.
          </p>
          <pre className="max-w-md overflow-auto rounded bg-background/50 p-2 text-xs text-foreground/50">
            {error.message}
          </pre>
          <button
            onClick={this.reset}
            className="rounded bg-brand-primary px-4 py-2 text-sm font-bold text-white transition-opacity hover:opacity-90 dark:bg-brand-accent dark:text-background"
          >
            다시 시도
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
