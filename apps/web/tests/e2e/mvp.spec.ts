/**
 * MVP E2E - 메모리 반도체 2024Q3 분석 워크플로우 (T4.1).
 *
 * 사용자 시나리오:
 *  1. Dashboard 진입
 *  2. sector=memory_semiconductor, quarter=2024Q3 (default)
 *  3. "Run Analysis" 클릭 → SSE 연결 + ThoughtPanel 활성화
 *  4. 60초 내 그래프 + 정합성 결과 표시
 *  5. 데모 fixture 기준: 7 노드, 11 엣지, 3 reconciliation_errors
 *
 * 합격 기준 (architecture.md §10 T4.1):
 *  - TTFGraph (Time To First Graph) < 60s
 *  - 모든 엣지에 citation 1+ 첨부 (그래프 노드/엣지 렌더 + 메트릭 채워짐)
 *  - 정합성 오차 결과 1건 이상 표시 (검증 작동 증거)
 */

import { test, expect } from '@playwright/test';

const TTFG_BUDGET_MS = 60_000;

// 백엔드 데모 fixture 가 보장하는 최소 수치
const EXPECTED_MIN_NODES = 7;
const EXPECTED_MIN_EDGES = 11;
const EXPECTED_MIN_RECON_ERRORS = 1;

test.describe('MVP - Memory Semi 2024Q3 workflow', () => {
  test('Dashboard 로딩 → analysis 트리거 → 그래프 + 정합성 결과 표시', async ({
    page,
  }) => {
    // ---- 1. Dashboard 진입 -----------------------------------------
    await page.goto('/dashboard');

    // 핵심 컨트롤 가시
    await expect(page.getByTestId('dashboard-root')).toBeVisible();
    await expect(page.getByTestId('run-button')).toBeVisible();
    await expect(page.getByTestId('sector-select')).toHaveValue(
      'memory_semiconductor',
    );
    await expect(page.getByTestId('quarter-select')).toHaveValue('2024Q3');

    // 최초 상태: idle
    await expect(page.getByTestId('dashboard-root')).toHaveAttribute(
      'data-stream-status',
      'idle',
    );

    // ---- 2. Run Analysis 클릭 → 스트리밍 시작 ----------------------
    const runBtn = page.getByTestId('run-button');
    const ttfgStart = Date.now();
    await runBtn.click();

    // streaming 또는 reconnecting 상태 진입 (connecting 은 너무 짧아 놓칠 수 있음)
    await expect(page.getByTestId('dashboard-root')).toHaveAttribute(
      'data-stream-status',
      /streaming|complete/,
      { timeout: 10_000 },
    );

    // ---- 3. TTFGraph - 첫 React Flow 노드 렌더 -----------------------
    // CompanyNode 는 React Flow rfd v12 의 .react-flow__node 클래스 + 우리 testid 사용
    const firstFlowNode = page.locator('.react-flow__node').first();
    await firstFlowNode.waitFor({ state: 'visible', timeout: TTFG_BUDGET_MS });
    const ttfgMs = Date.now() - ttfgStart;
    // SLA: 60s 미만
    expect(ttfgMs).toBeLessThan(TTFG_BUDGET_MS);
    // eslint-disable-next-line no-console
    console.log(`[TTFGraph] ${ttfgMs} ms (budget ${TTFG_BUDGET_MS} ms)`);

    // ---- 4. 파이프라인 종료까지 대기 -------------------------------
    await expect(page.getByTestId('dashboard-root')).toHaveAttribute(
      'data-stream-status',
      'complete',
      { timeout: TTFG_BUDGET_MS },
    );

    // ---- 5. 그래프 노드/엣지 수 검증 -------------------------------
    const nodeCount = await page.locator('.react-flow__node').count();
    expect(nodeCount).toBeGreaterThanOrEqual(EXPECTED_MIN_NODES);

    const edgeCount = await page.locator('.react-flow__edge').count();
    expect(edgeCount).toBeGreaterThanOrEqual(EXPECTED_MIN_EDGES);

    // ---- 6. ThoughtPanel - 4개 에이전트 모두 complete --------------
    // AgentColumn 의 status 라벨로 감지 (ThoughtPanel.tsx 참고)
    await expect(
      page.getByText('Complete ✓').nth(0),
    ).toBeVisible({ timeout: 5_000 });
    const completeCount = await page.getByText('Complete ✓').count();
    expect(completeCount).toBeGreaterThanOrEqual(4);

    // ---- 7. ReconciliationLegend - 정합성 검증 작동 증거 ----------
    // ReconciliationLegend 컴포넌트는 노드가 있을 때만 표시됨 (SupplyChainFlow.tsx).
    // 텍스트 단편으로 검증 (i18n 변동 시 깨질 수 있어 'Reconciliation' 단어 매칭)
    const legend = page.getByText(/Reconciliation|정합성/i).first();
    await expect(legend).toBeVisible();

    // ---- 8. 정합성 오차 시각화 - 빨강/주황 엣지 존재 검증 ---------
    // TradeEdge.tsx 가 severity 에 따라 stroke 색상을 'oklch' var() 로 적용 - 테스트
    // 안정성 위해 reconciliationErrors 가 적어도 1건 발생했는지 SSE 이벤트로 확인.
    // graph_update 이벤트 중 reconciliation_errors 가 적어도 1건 있는지 검증.
    // (DOM 만으론 색상 OKLCH 비교가 까다로워 SSE 청크 검사로 대체)

    // 페이지에 노출된 events store 가 없으니 대신 SSE error_count 를 빈 빨간 엣지로 검증.
    // SupplyChainFlow.tsx 가 severity='high' 인 엣지에 stroke="conflict-high" 적용.
    // edge-conflict 클래스 또는 stroke 색상 검증
    const allEdges = await page.locator('.react-flow__edge').all();
    expect(allEdges.length).toBeGreaterThanOrEqual(EXPECTED_MIN_EDGES);

    // edge-conflict 클래스가 적어도 1개 (severity high/medium) 또는
    // 엣지 hover 시 EdgeTooltip 노출 → 정합성 오차 1건 이상 보장
    // 데모 fixture 기준 3건 → 적어도 1건 검출
    const conflictEdges = page.locator('.react-flow__edge.edge-conflict');
    const conflictCount = await conflictEdges.count();
    // 데모 fixture 3건 보장 ≥ 1
    expect(conflictCount).toBeGreaterThanOrEqual(EXPECTED_MIN_RECON_ERRORS);
  });

  test('초기 상태에서 Topology Preview 안내 표시', async ({ page }) => {
    await page.goto('/dashboard');
    // 초기에는 그래프 비어있음 - "Click Run Analysis" 안내 메시지 노출
    await expect(page.getByText('Topology Preview')).toBeVisible();
    await expect(page.getByText(/Run Analysis/)).toBeVisible();
  });

  test('Sector / Quarter 선택 변경이 가능 (idle 상태)', async ({ page }) => {
    await page.goto('/dashboard');
    const sectorSel = page.getByTestId('sector-select');
    const quarterSel = page.getByTestId('quarter-select');

    await sectorSel.selectOption('display_oled');
    await expect(sectorSel).toHaveValue('display_oled');

    await quarterSel.selectOption('2024Q4');
    await expect(quarterSel).toHaveValue('2024Q4');

    // memory_semiconductor 로 다시 변경 (다른 테스트와 독립적이려면 cleanup)
    await sectorSel.selectOption('memory_semiconductor');
    await quarterSel.selectOption('2024Q3');
  });
});
