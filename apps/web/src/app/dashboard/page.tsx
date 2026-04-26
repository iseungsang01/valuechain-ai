'use client';

import { useState } from 'react';
import { SupplyChainFlow } from '../../components/graph/SupplyChainFlow';
import { ThoughtPanel } from '../../components/agent-stream/ThoughtPanel';
import { ErrorBoundary } from '../../components/error/ErrorBoundary';
import { AgentErrorPanel } from '../../components/error/AgentErrorPanel';
import { useAgentStream } from '../../hooks/useAgentStream';

export default function DashboardPage() {
  const [sector, setSector] = useState('memory_semiconductor');
  const [quarter, setQuarter] = useState('2024Q3');

  const {
    events,
    status,
    start,
    stop,
    retry,
    error,
    agentError,
    reconnectAttempt,
    maxReconnects,
  } = useAgentStream();

  const isBusy = status === 'streaming' || status === 'connecting' || status === 'reconnecting';

  const handleRun = () => {
    if (isBusy) {
      stop();
    } else {
      start(sector, quarter);
    }
  };

  const buttonLabel = (() => {
    if (status === 'streaming') return '분석 중지';
    if (status === 'connecting') return '연결 중...';
    if (status === 'reconnecting') return `재연결 중 ${reconnectAttempt}/${maxReconnects}`;
    return '분석 시작';
  })();

  return (
    <main
      data-testid="dashboard-root"
      data-stream-status={status}
      className="h-screen w-full flex flex-col p-4 gap-4 bg-background"
    >
      <header className="flex items-center justify-between bg-background/50 border border-foreground/10 rounded-lg p-4 shadow-sm">
        <div>
          <h1 className="text-xl font-bold text-foreground">ValueChain AI</h1>
          <p className="text-xs text-foreground/60 mt-1">
            공급망 정합성 &amp; 충돌 탐지
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <select
              data-testid="sector-select"
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              disabled={isBusy}
              className="bg-background border border-foreground/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-brand-primary"
            >
              <option value="memory_semiconductor">Memory Semiconductor</option>
              <option value="display_oled">Display OLED</option>
              <option value="battery_secondary">Secondary Battery</option>
            </select>

            <select
              data-testid="quarter-select"
              value={quarter}
              onChange={(e) => setQuarter(e.target.value)}
              disabled={isBusy}
              className="bg-background border border-foreground/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-brand-primary"
            >
              <option value="2024Q3">2024 Q3</option>
              <option value="2024Q4">2024 Q4</option>
              <option value="2025Q1">2025 Q1</option>
            </select>
          </div>

          <button
            data-testid="run-button"
            onClick={handleRun}
            disabled={status === 'connecting'}
            className={`px-6 py-1.5 rounded font-bold text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              isBusy
                ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20 border border-red-500/20'
                : 'bg-brand-primary text-white hover:bg-brand-primary/90 dark:bg-brand-accent dark:text-background dark:hover:bg-brand-accent/90'
            }`}
          >
            {buttonLabel}
          </button>
        </div>
      </header>

      {/* T4.2: 분류된 SSE 에러 패널 - 카테고리별 색상/아이콘 + 재시도/재연결 */}
      {agentError && (
        <AgentErrorPanel
          error={agentError}
          onRetry={retry}
          reconnectAttempt={status === 'reconnecting' ? reconnectAttempt : 0}
          maxReconnects={maxReconnects}
          onDismiss={() => stop()}
        />
      )}

      {/* 폴백 - 분류된 에러가 없는 단순 문자열 에러 (네트워크 등) */}
      {!agentError && error && (
        <div
          role="alert"
          data-testid="generic-error-banner"
          className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-2 rounded-lg text-sm flex items-center justify-between"
        >
          <span>{error}</span>
          <button
            onClick={() => stop()}
            className="text-red-500 hover:text-red-700"
            aria-label="에러 메시지 닫기"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex-1 flex gap-4 min-h-0">
        <ErrorBoundary>
          <div className="w-[60%] h-full" data-testid="supply-chain-container">
            <SupplyChainFlow />
          </div>
        </ErrorBoundary>
        <ErrorBoundary>
          <div className="w-[40%] h-full" data-testid="thought-panel-container">
            <ThoughtPanel events={events} status={status} />
          </div>
        </ErrorBoundary>
      </div>
    </main>
  );
}
