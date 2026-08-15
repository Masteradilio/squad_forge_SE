import type { APIRequestContext } from '@playwright/test';
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

test.beforeEach(async ({ request }) => {
  await requireBackend(request);
});

test('compiled frontend smoke requires the backend contract', async ({ page }, testInfo) => {
  const response = await page.goto('/');
  expect(response?.ok(), 'compiled frontend must return a successful document response').toBeTruthy();
  await expect(page.getByRole('heading', { name: 'ForgeOS Cloud', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'LocalForge sections' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Chat \+ Pipeline\/Kanban Workspace/ })).toHaveAttribute('aria-current', 'page');
  await page.screenshot({ path: testInfo.outputPath('frontend-smoke.png'), fullPage: true });
});
