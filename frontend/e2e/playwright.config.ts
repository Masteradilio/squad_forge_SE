import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.FRONTEND_BASE_URL?.trim();
if (!baseURL) {
  throw new Error('FRONTEND_BASE_URL is required. Point it to the compiled frontend or a Kubernetes port-forward.');
}

const outputDir = process.env.E2E_OUTPUT_DIR?.trim() || 'test-results';
const htmlReportDir = process.env.E2E_HTML_REPORT_DIR?.trim() || 'playwright-report';

export default defineConfig({
  testDir: '.',
  outputDir,
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: htmlReportDir, open: 'never' }],
  ],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile',
      use: { ...devices['Pixel 5'] },
    },
  ],
});
