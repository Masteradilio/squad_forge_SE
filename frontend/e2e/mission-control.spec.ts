import type { APIRequestContext, Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function requireBackend(request: APIRequestContext) {
  let response;
  try {
    response = await request.get('/api/projects');
  } catch (error) {
    throw new Error(`Backend obrigatório indisponível via FRONTEND_BASE_URL: ${String(error)}`, { cause: error });
  }

  if (!response.ok()) {
    throw new Error(`Backend obrigatório indisponível: GET /api/projects retornou HTTP ${response.status()}.`);
  }

  const payload: unknown = await response.json();
  if (!Array.isArray(payload)) {
    throw new Error('Backend obrigatório inválido: GET /api/projects não retornou uma lista.');
  }
}

async function visitSection(page: Page, name: RegExp, hash: string, content: RegExp) {
  const link = page.getByRole('link', { name });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(new RegExp(`#/${hash}$`));
  await expect(link).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('main')).toContainText(content);
}

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test('unified workspace visual journey exposes the full delivery pipeline', async ({ page }, testInfo) => {
  const response = await page.goto('/');
  expect(response?.ok(), 'compiled frontend must return a successful document response').toBeTruthy();

  await expect(page.getByRole('heading', { name: 'ForgeOS Cloud', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'LocalForge sections' })).toBeVisible();
  await expect(page.getByText(/Do documento ao software entregue/)).toBeVisible();
  await expect(page.getByRole('link', { name: /Chat \+ Pipeline\/Kanban Workspace/ })).toHaveAttribute('aria-current', 'page');

  await visitSection(page, /Chat \+ Pipeline\/Kanban/, 'chat', /Backlog|Security Auditor|Tester final/);
  await visitSection(page, /Telemetria/, 'tests', /Telemetria|Conformidade|Security Auditor|E2E Release Tester/);
  await visitSection(page, /Skills/, 'skills', /Skills|Agentes/);
  await visitSection(page, /Modelos/, 'settings', /OmniRoute|Model|BYOK/);

  await page.screenshot({ path: testInfo.outputPath('mission-control-journey.png'), fullPage: true });
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(dimensions.width, 'responsive journey must not create horizontal overflow').toBeLessThanOrEqual(dimensions.viewport + 2);
});
