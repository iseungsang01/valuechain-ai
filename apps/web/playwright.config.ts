/**
 * Playwright config - Phase 1 MVP E2E (T4.1).
 *
 * 동작 방식:
 *  - testDir = ./tests/e2e
 *  - webServer 배열: Next.js + FastAPI 둘 다 자동 spawn (`reuseExistingServer=true`).
 *  - 프로젝트: chromium, firefox 두 가지 (webkit 은 Windows 안정성 이슈로 제외).
 *
 * CI 친화:
 *  - retries=2 (CI), 0 (로컬)
 *  - workers=1 (서버 충돌 방지) - SSE 동시연결 안정성 우선
 *  - reporter: list + html (test-results/playwright-report)
 */

import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const isCI = !!process.env.CI;
const repoRoot = path.resolve(__dirname, '..', '..');
const apiVenvPython = path.join(repoRoot, 'apps', 'api', '.venv', 'Scripts', 'python.exe');

export default defineConfig({
  testDir: './tests/e2e',
  // 단일 테스트 타임아웃 - SSE 파이프라인 60s 여유
  timeout: 90_000,
  expect: { timeout: 15_000 },

  fullyParallel: false, // SSE 동시 연결 충돌 방지
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: 1,

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results',

  use: {
    baseURL: process.env.E2E_WEB_BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // 한국어 locale - 백엔드 메시지 일관성
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
  ],

  webServer: [
    {
      // Next.js - production build 후 start.
      // 빌드 시 NEXT_PUBLIC_API_BASE_URL 가 inline 됨 → 기본값 'http://localhost:8000' 사용.
      command: 'npm run start',
      cwd: __dirname,
      port: 3000,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // FastAPI - apps/api/.venv 의 uvicorn 사용.
      // LangGraph + Pydantic + httpx 임포트가 무거워 cold start 가 길어질 수 있음 (Windows).
      // CORS 는 settings.py 기본값 (localhost:3000, localhost:8000) 으로 충분.
      command: `"${apiVenvPython}" -m uvicorn main:app --host 0.0.0.0 --port 8000 --no-access-log`,
      cwd: path.resolve(repoRoot, 'apps', 'api'),
      // 포트 probe (URL probe 가 Windows 에서 hang 하는 이슈 회피)
      port: 8000,
      reuseExistingServer: !isCI,
      timeout: 180_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        // CORS - localhost 두 포트 + 127.0.0.1 도 허용 (브라우저 분기 안전)
        CORS_ORIGINS:
          'http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000',
      },
    },
  ],
});
