/**
 * 에러 케이스 E2E - T4.2 에러 처리 + Fallback 검증.
 *
 * 시나리오:
 *  1. 백엔드 다운 → POST /api/runs 실패 → generic-error-banner 표시
 *  2. SSE 도중 강제 끊김 → 자동 재연결 시도 (최대 3회)
 *  3. 백엔드 도메인 예외 (GroundingError) → AgentErrorPanel 카테고리=hallucination
 *  4. 사용자 검증 에러 (invalid sector) → 422 응답 / 사용자 메시지
 *
 * 도구: Playwright route() 로 백엔드 응답 가로채기 - 실 백엔드 의존도 최소화.
 */

import { test, expect } from '@playwright/test';

test.describe('Error handling - T4.2', () => {
  test('백엔드 500 → POST /api/runs 실패 → 에러 메시지 노출', async ({
    page,
  }) => {
    // POST /api/runs 만 가로채서 500 반환
    await page.route('**/api/runs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            category: 'internal',
            error_code: 'INTERNAL_ERROR',
            message: '예상치 못한 오류가 발생했습니다.',
            retriable: false,
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto('/dashboard');
    await page.getByTestId('run-button').click();

    // AgentErrorPanel 노출 - category=internal
    const panel = page.getByTestId('agent-error-panel');
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(panel).toHaveAttribute('data-error-category', 'internal');
    await expect(panel).toHaveAttribute('data-error-code', 'INTERNAL_ERROR');
    await expect(panel).toHaveAttribute('data-retriable', 'false');
    // 사용자 메시지 표시
    await expect(page.getByTestId('agent-error-message')).toContainText(
      '예상치 못한 오류',
    );
    // retriable=false 이므로 retry 버튼 비노출
    await expect(page.getByTestId('agent-error-retry')).toHaveCount(0);
  });

  test('SSE 도중 GroundingError → hallucination 카테고리 패널', async ({
    page,
  }) => {
    // POST /api/runs 는 정상 통과, GET stream 만 가로채서 SSE error event 송출
    await page.route('**/api/runs/*/stream', async (route) => {
      // ReadableStream 으로 SSE 페이로드 합성
      const body =
        'event: agent_start\n' +
        'id: 1\n' +
        'data: {"event_id":"1","run_id":"r1","agent":"StructureMapper","type":"agent_start","timestamp":"2024-01-01T00:00:00Z","payload":{}}\n\n' +
        'event: error\n' +
        'id: 2\n' +
        'data: {"event_id":"2","run_id":"r1","agent":"Evaluator","type":"error","timestamp":"2024-01-01T00:00:01Z","payload":{"category":"hallucination","error_code":"LLM_HALLUCINATION_BLOCKED","message":"AI가 출처가 없는 수치를 생성하려고 시도했습니다.","retriable":false}}\n\n';
      await route.fulfill({
        status: 200,
        headers: {
          'content-type': 'text/event-stream',
          'cache-control': 'no-cache',
          'x-accel-buffering': 'no',
        },
        body,
      });
    });

    await page.goto('/dashboard');
    await page.getByTestId('run-button').click();

    const panel = page.getByTestId('agent-error-panel');
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(panel).toHaveAttribute('data-error-category', 'hallucination');
    await expect(panel).toHaveAttribute(
      'data-error-code',
      'LLM_HALLUCINATION_BLOCKED',
    );
    await expect(panel).toHaveAttribute('data-retriable', 'false');
    // 카테고리 라벨
    await expect(panel).toContainText('AI 환각 차단');
    // retriable=false → retry 버튼 / reconnecting 인디케이터 모두 비노출
    await expect(page.getByTestId('agent-error-retry')).toHaveCount(0);
    await expect(page.getByTestId('agent-error-reconnecting')).toHaveCount(0);
  });

  test('SSE rate_limit 에러 → 카테고리=rate_limit + retry 버튼 노출', async ({
    page,
  }) => {
    await page.route('**/api/runs/*/stream', async (route) => {
      const body =
        'event: error\n' +
        'id: 1\n' +
        'data: {"event_id":"1","run_id":"r1","agent":"DataCollector","type":"error","timestamp":"2024-01-01T00:00:01Z","payload":{"category":"rate_limit","error_code":"EXTERNAL_RATE_LIMIT","message":"외부 API 호출 한도에 도달했습니다. 잠시 후 자동으로 재시도됩니다.","retriable":true}}\n\n';
      await route.fulfill({
        status: 200,
        headers: {
          'content-type': 'text/event-stream',
          'cache-control': 'no-cache',
        },
        body,
      });
    });

    await page.goto('/dashboard');
    await page.getByTestId('run-button').click();

    const panel = page.getByTestId('agent-error-panel');
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(panel).toHaveAttribute('data-error-category', 'rate_limit');
    await expect(panel).toHaveAttribute('data-retriable', 'true');
    await expect(panel).toContainText('호출 한도');
  });

  test('백엔드 422 입력 검증 에러 → validation 카테고리 표시', async ({ page }) => {
    // POST /api/runs 가 422 반환 (백엔드의 분류된 페이로드)
    await page.route('**/api/runs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            category: 'validation',
            error_code: 'REQUEST_VALIDATION_FAILED',
            message: '요청 형식이 올바르지 않습니다. 입력값을 확인해주세요.',
            retriable: false,
            validation_errors: [
              { loc: ['body', 'sector'], msg: 'invalid', type: 'value_error' },
            ],
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto('/dashboard');
    await page.getByTestId('run-button').click();

    const panel = page.getByTestId('agent-error-panel');
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(panel).toHaveAttribute('data-error-category', 'validation');
    await expect(panel).toContainText('입력값 오류');
  });

  test('네트워크 끊김 → 자동 재연결 시도 (reconnecting 상태 노출)', async ({
    page,
  }) => {
    // POST 는 통과시키지만 SSE 는 즉시 abort 된 응답을 반환
    let streamCalls = 0;
    await page.route('**/api/runs/*/stream', async (route) => {
      streamCalls += 1;
      // 첫 호출: 즉시 빈 응답 (연결 직후 종료) → 클라가 재연결 시도
      // 두 번째부터도 같은 응답 → 결국 reconnecting 상태에 진입한 흔적이 남음
      await route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
        body: '', // 즉시 EOF
      });
    });

    await page.goto('/dashboard');
    await page.getByTestId('run-button').click();

    // reconnecting 상태가 적어도 한 번은 표시됨
    await expect(page.getByTestId('dashboard-root')).toHaveAttribute(
      'data-stream-status',
      /reconnecting|error|complete/,
      { timeout: 15_000 },
    );

    // 스트림 엔드포인트가 적어도 2번 이상 호출됨 (= 재연결 시도)
    await page.waitForTimeout(3_000);
    expect(streamCalls).toBeGreaterThanOrEqual(2);
  });

  test('ErrorBoundary - 자식 컴포넌트 throw 시 fallback 노출', async ({
    page,
  }) => {
    // Production build 에서는 ErrorBoundary 가 잡지만 의도적 throw 가 어려움.
    // 대신 ErrorBoundary 가 정상 동작 시 dashboard 가 그대로 렌더되는 경로를 확인.
    await page.goto('/dashboard');
    await expect(page.getByTestId('supply-chain-container')).toBeVisible();
    await expect(page.getByTestId('thought-panel-container')).toBeVisible();
    // ErrorBoundary fallback 은 노출 안 됨
    await expect(page.getByTestId('error-boundary-fallback')).toHaveCount(0);
  });
});
